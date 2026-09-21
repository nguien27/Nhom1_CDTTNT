"""Pipeline chính GĐ3-02.

GĐ3-01 -> Information Extraction / GĐ2-02 Schema Mapping -> Confidence ->
Validation -> output cho GĐ3-03.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .confidence import ConfidenceManager
from .constants import REQUIRED_FIELDS, STANDARD_FIELDS, VALIDATION_ERRORS
from .gd2_02_mapping_adapter import GD202SchemaMappingAdapter
from .gd3_01_adapter import read_file, read_raw_text
from .information_extractor import InformationExtractor
from .models import EmployeeRecord, ExtractionResult, MappingCandidate, ValidationResult
from .validator import Validator


class InformationExtractionPipeline:
    def __init__(self, use_ai: bool = False, ai_client=None):
        self.extractor = InformationExtractor(use_ai=use_ai, ai_client=ai_client)
        self.mapper = GD202SchemaMappingAdapter()
        self.validator = Validator()
        self.confidence_manager = ConfidenceManager()

    def process_file(self, file_path: str) -> ExtractionResult:
        return self.process_contract(read_file(file_path))

    def process_raw_text(self, raw_text: str) -> ExtractionResult:
        return self.process_contract(read_raw_text(raw_text))

    def process_contract(self, input_data: Dict[str, Any]) -> ExtractionResult:
        if not isinstance(input_data, dict):
            return self._error_result("UPSTREAM_ERROR", "Input contract phải là dict.")

        status = input_data.get("status")
        success = input_data.get("success")
        error = input_data.get("error")
        if status == "error" or success is False or error:
            message = self._upstream_error_message(error)
            return self._error_result("UPSTREAM_ERROR", message, metadata={"upstream_error": error})

        tables = [table for table in (input_data.get("tables") or []) if isinstance(table, dict)]
        text = str(input_data.get("text") or "").strip()
        metadata = dict(input_data.get("metadata") or {})
        metadata.update(
            {
                "input_source_type": input_data.get("source_type", "unknown"),
                "reader": metadata.get("source_module", "GD3-01"),
                "pages": list(input_data.get("pages") or []),
                "reader_warnings": list(input_data.get("warnings") or []),
                "schema_mapping_upstream": "GD2-02",
                "gd2_02_available": self.mapper.upstream_available,
            }
        )
        if self.mapper.predictor_error:
            metadata["gd2_02_warning"] = self.mapper.predictor_error

        input_source_type = str(input_data.get("source_type") or "").lower()
        if input_source_type in {"txt", "raw_string"}:
            semantic_tables, table_mappings = [], {}
        else:
            semantic_tables, table_mappings = self._select_semantic_tables(tables)
        if semantic_tables:
            result = self._process_tables(semantic_tables, table_mappings, metadata)
            result.metadata["text_ignored_because_structured_table_present"] = bool(text)
            return result

        if text:
            return self._process_text(text, metadata)

        return self._error_result("EMPLOYEE_NOT_FOUND", VALIDATION_ERRORS["EMPLOYEE_NOT_FOUND"], metadata=metadata)

    # API tương thích code cũ.
    def process_structured(self, file_path: str) -> ExtractionResult:
        return self.process_file(file_path)

    def process_unstructured(
        self,
        file_path: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> ExtractionResult:
        if file_path:
            return self.process_file(file_path)
        if raw_text is not None:
            return self.process_raw_text(raw_text)
        return self._error_result("EMPTY_INPUT", VALIDATION_ERRORS["EMPTY_INPUT"])

    def _select_semantic_tables(
        self,
        tables: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[int, List[MappingCandidate]]]:
        semantic: List[Dict[str, Any]] = []
        mapping_by_id: Dict[int, List[MappingCandidate]] = {}

        for table in tables:
            if str(table.get("kind") or "").lower() == "key_value":
                continue
            rows = list(table.get("rows") or [])
            headers = list(table.get("headers") or [])
            if not headers and rows and isinstance(rows[0], dict):
                headers = list(rows[0].keys())
            if not rows or not headers:
                continue

            mappings = self.mapper.map_headers([str(header) for header in headers])
            recognized = {
                mapping.target
                for mapping in mappings
                if mapping.accepted and mapping.target in STANDARD_FIELDS
            }
            # "noi_dung" từ DOCX/PDF text carrier không được coi là bảng nhân sự.
            is_semantic = len(recognized) >= 2 or bool(recognized.intersection(REQUIRED_FIELDS))
            if is_semantic:
                table_copy = dict(table)
                table_copy["headers"] = headers
                semantic.append(table_copy)
                mapping_by_id[id(table_copy)] = mappings

        return semantic, mapping_by_id

    def _process_tables(
        self,
        tables: List[Dict[str, Any]],
        mapping_by_id: Dict[int, List[MappingCandidate]],
        metadata: Dict[str, Any],
    ) -> ExtractionResult:
        records: List[EmployeeRecord] = []
        all_mappings: List[MappingCandidate] = []

        for table_index, table in enumerate(tables, start=1):
            rows = list(table.get("rows") or [])
            mappings = mapping_by_id.get(id(table)) or self.mapper.map_headers(list(table.get("headers") or []))
            all_mappings.extend(mappings)

            for row_index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    continue
                record = self._record_from_row(row, mappings, metadata)
                record.raw_data = {
                    "table_index": table_index,
                    "row_index": row_index,
                    "table_name": table.get("name") or table.get("sheet_name"),
                    "row": dict(row),
                }
                records.append(record)

        validation = self.validator.validate_records(records)
        confirmation_items = self._confirmation_items(records)
        return ExtractionResult(
            records=records,
            validation=validation,
            metadata={
                **metadata,
                "source_type": "structured",
                "table_count": len(tables),
                "record_count": len(records),
                "mapping_count": len(all_mappings),
                "mapper": "GD2-02 + GĐ3-02 extension aliases",
            },
            requires_user_confirmation=bool(confirmation_items),
            confirmation_items=confirmation_items,
        )

    def _record_from_row(
        self,
        row: Dict[str, Any],
        mappings: List[MappingCandidate],
        metadata: Dict[str, Any],
    ) -> EmployeeRecord:
        record = EmployeeRecord(
            source_type="structured",
            source_file=metadata.get("filename") or metadata.get("source_file"),
            mappings=[MappingCandidate(**mapping.to_dict()) for mapping in mappings],
        )

        best_by_target: Dict[str, MappingCandidate] = {}
        for mapping in mappings:
            if not mapping.accepted or mapping.target not in STANDARD_FIELDS:
                continue
            current = best_by_target.get(str(mapping.target))
            if current is None or mapping.confidence > current.confidence:
                best_by_target[str(mapping.target)] = mapping

        for target, mapping in best_by_target.items():
            if mapping.source not in row:
                continue
            value = row.get(mapping.source)
            if value is None or not str(value).strip():
                continue
            normalized_value = str(value).strip()
            if target == "ma_nhan_vien":
                normalized_value = normalized_value.upper()
            if target == "email":
                normalized_value = normalized_value.lower()
            setattr(record, target, normalized_value)
            record.confidence_scores[target] = mapping.confidence

        return record

    def _process_text(self, text: str, metadata: Dict[str, Any]) -> ExtractionResult:
        groups = self.extractor.extract_records(text)
        records = [self._record_from_fields(fields, metadata) for fields in groups]
        validation = self.validator.validate_records(records)
        confirmation_items = self._confirmation_items(records)
        return ExtractionResult(
            records=records,
            validation=validation,
            metadata={
                **metadata,
                "source_type": "unstructured",
                "text_length": len(text),
                "record_count": len(records),
                "multiple_employees": len(records) > 1,
                "mapper": "Information Extraction -> GĐ2-02 mapping contract",
            },
            requires_user_confirmation=bool(confirmation_items),
            confirmation_items=confirmation_items,
        )

    def _record_from_fields(self, fields, metadata: Dict[str, Any]) -> EmployeeRecord:
        mappings = self.mapper.map_extracted_fields(fields)
        record = EmployeeRecord(
            source_type="unstructured",
            source_file=metadata.get("filename") or metadata.get("source_file"),
            mappings=mappings,
            raw_data={"extracted_fields": [field.to_dict() for field in fields]},
        )

        for field in fields:
            if field.field_name not in STANDARD_FIELDS:
                continue
            old_score = record.confidence_scores.get(field.field_name, -1.0)
            if field.confidence <= old_score:
                continue
            value = field.value
            if field.field_name == "ma_nhan_vien":
                value = str(value).upper()
            if field.field_name == "email":
                value = str(value).lower()
            setattr(record, field.field_name, value)
            record.confidence_scores[field.field_name] = field.confidence

        return record

    def _confirmation_items(self, records: List[EmployeeRecord]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for record_index, record in enumerate(records, start=1):
            items.extend(
                self.confidence_manager.get_confirmation_items(
                    record.mappings,
                    record_index=record_index,
                )
            )
        return items

    @staticmethod
    def _upstream_error_message(error: Any) -> str:
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        return str(error or VALIDATION_ERRORS["UPSTREAM_ERROR"])

    @staticmethod
    def _error_result(
        code: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        validation = ValidationResult(is_valid=False)
        validation.add_error(code, message)
        return ExtractionResult(
            records=[],
            validation=validation,
            metadata=dict(metadata or {}),
            requires_user_confirmation=False,
            confirmation_items=[],
        )


def run_pipeline(
    file_path: Optional[str] = None,
    raw_text: Optional[str] = None,
    input_contract: Optional[Dict[str, Any]] = None,
    use_ai: bool = False,
    ai_client=None,
) -> ExtractionResult:
    pipeline = InformationExtractionPipeline(use_ai=use_ai, ai_client=ai_client)
    if input_contract is not None:
        return pipeline.process_contract(input_contract)
    if file_path:
        return pipeline.process_file(file_path)
    if raw_text is not None:
        return pipeline.process_raw_text(raw_text)
    return pipeline._error_result("EMPTY_INPUT", VALIDATION_ERRORS["EMPTY_INPUT"])
