"""Validation độc lập cho kết quả GĐ3-02."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .constants import CONFIRMATION_THRESHOLD, REQUIRED_FIELDS, STANDARD_FIELDS, VALIDATION_ERRORS
from .models import EmployeeRecord, MappingCandidate, ValidationResult


class Validator:
    def validate_record(self, record: EmployeeRecord) -> ValidationResult:
        result = ValidationResult(is_valid=True)

        for field_name in REQUIRED_FIELDS:
            value = getattr(record, field_name, None)
            if value is None or not str(value).strip():
                code = f"MISSING_{field_name.upper()}"
                result.add_error(code, VALIDATION_ERRORS.get(code, f"Thiếu {field_name}."), field=field_name)

        duplicates = self.find_duplicate_mappings(record.mappings)
        if duplicates:
            result.add_error(
                "DUPLICATE_MAPPING",
                VALIDATION_ERRORS["DUPLICATE_MAPPING"],
                duplicate_mappings=duplicates,
            )

        unknown = self.find_unknown_fields(record.mappings)
        if unknown:
            result.add_warning(
                "UNKNOWN_FIELD",
                VALIDATION_ERRORS["UNKNOWN_FIELD"],
                fields=unknown,
            )

        low_confidence = self.find_low_confidence(record)
        if low_confidence:
            result.add_warning(
                "LOW_CONFIDENCE",
                VALIDATION_ERRORS["LOW_CONFIDENCE"],
                fields=low_confidence,
            )

        return result

    def validate_records(self, records: List[EmployeeRecord]) -> ValidationResult:
        if not records:
            result = ValidationResult(is_valid=False)
            result.add_error("EMPLOYEE_NOT_FOUND", VALIDATION_ERRORS["EMPLOYEE_NOT_FOUND"])
            return result

        final = ValidationResult(is_valid=True)
        per_record: List[Dict] = []

        for index, record in enumerate(records, start=1):
            current = self.validate_record(record)
            if not current.is_valid:
                final.is_valid = False
            for item in current.errors:
                final.errors.append({**item, "record_index": index})
            for item in current.warnings:
                final.warnings.append({**item, "record_index": index})
            per_record.append({"record_index": index, "validation": current.to_dict()})

        if len(records) > 1:
            final.add_warning(
                "MULTIPLE_EMPLOYEES",
                VALIDATION_ERRORS["MULTIPLE_EMPLOYEES"],
                employee_count=len(records),
            )

        final.details["records"] = per_record
        final.details["employee_count"] = len(records)
        return final

    @staticmethod
    def find_duplicate_mappings(mappings: List[MappingCandidate]) -> List[Dict]:
        grouped: dict[str, List[str]] = defaultdict(list)
        for mapping in mappings:
            if mapping.accepted and mapping.target in STANDARD_FIELDS:
                grouped[str(mapping.target)].append(mapping.source)

        duplicates: List[Dict] = []
        for target, sources in grouped.items():
            unique_sources = list(dict.fromkeys(sources))
            if len(unique_sources) > 1:
                duplicates.append({"target": target, "sources": unique_sources})
        return duplicates

    @staticmethod
    def find_unknown_fields(mappings: List[MappingCandidate]) -> List[str]:
        values = [
            mapping.source
            for mapping in mappings
            if not mapping.accepted or mapping.target not in STANDARD_FIELDS
        ]
        return list(dict.fromkeys(values))

    @staticmethod
    def find_low_confidence(record: EmployeeRecord) -> List[Dict]:
        values: List[Dict] = []
        seen: set[tuple] = set()

        for field_name, score in record.confidence_scores.items():
            if float(score) < CONFIRMATION_THRESHOLD:
                key = (field_name, None)
                if key not in seen:
                    values.append({"field": field_name, "confidence": float(score)})
                    seen.add(key)

        for mapping in record.mappings:
            if mapping.target and mapping.confidence < CONFIRMATION_THRESHOLD:
                key = (mapping.target, mapping.source)
                if key not in seen:
                    values.append(
                        {
                            "field": mapping.target,
                            "source": mapping.source,
                            "confidence": mapping.confidence,
                        }
                    )
                    seen.add(key)
        return values


def validate_records(records: List[EmployeeRecord]):
    return Validator().validate_records(records)
