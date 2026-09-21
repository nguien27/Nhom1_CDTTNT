from __future__ import annotations

from typing import Any, Dict, List

from experiments.gd3_02_information_mapping.src.constants import CONFIRMATION_THRESHOLD
from experiments.gd3_02_information_mapping.src.gd2_02_mapping_adapter import GD202SchemaMappingAdapter


TARGET_TO_UI = {
    "ma_nhan_vien": "MA_NHAN_VIEN",
    "ho_ten": "HO_TEN",
    "don_vi": "TEN_DON_VI",
    "ten_don_vi": "TEN_DON_VI",
    "loai_don_vi": "LOAI_DON_VI",  # legacy/internal compatibility
    "chuc_vu": "CHUC_VU",
    "email": "EMAIL",
    "extension": "EXTENSION",
    "ket_qua": "KET_QUA",
    "can_cu": "CAN_CU",
    "ma_quy_tac": "MA_QUY_TAC",
    "ten_quy_tac": "TEN_QUY_TAC",
}

UI_TO_TARGET = {value: key for key, value in TARGET_TO_UI.items()}

# Alias chỉ dùng để nhận diện tên cột/khóa do người dùng cung cấp.
# Các field không nằm trong SCHEMA_FIELDS[data_type] tự động bị IGNORE.
EXTRA_HEADER_ALIASES = {
    "ma_nhan_vien": "MA_NHAN_VIEN",
    "ma nhan vien": "MA_NHAN_VIEN",
    "mã nhân viên": "MA_NHAN_VIEN",
    "ma cbcs": "MA_NHAN_VIEN",
    "mã cbcs": "MA_NHAN_VIEN",
    "msnv": "MA_NHAN_VIEN",

    "ho_ten": "HO_TEN",
    "ho ten": "HO_TEN",
    "họ tên": "HO_TEN",
    "họ và tên": "HO_TEN",

    "ten_don_vi": "TEN_DON_VI",
    "ten don vi": "TEN_DON_VI",
    "tên đơn vị": "TEN_DON_VI",
    "don_vi": "TEN_DON_VI",
    "don vi": "TEN_DON_VI",
    "đơn vị": "TEN_DON_VI",
    "đơn vị công tác": "TEN_DON_VI",
    "tên đơn vị áp dụng": "TEN_DON_VI",

    "chuc_vu": "CHUC_VU",
    "chuc vu": "CHUC_VU",
    "chức vụ": "CHUC_VU",
    "vị trí": "CHUC_VU",

    "email": "EMAIL",
    "e-mail": "EMAIL",
    "gmail": "EMAIL",
    "email cá nhân": "EMAIL",
    "email ca nhan": "EMAIL",
    "địa chỉ email": "EMAIL",
    "dia chi email": "EMAIL",

    "extension": "EXTENSION",
    "máy lẻ": "EXTENSION",
    "may le": "EXTENSION",

    "ma_quy_tac": "MA_QUY_TAC",
    "ma quy tac": "MA_QUY_TAC",
    "mã quy tắc": "MA_QUY_TAC",
    "ma rule": "MA_QUY_TAC",
    "rule code": "MA_QUY_TAC",

    "ten_quy_tac": "TEN_QUY_TAC",
    "ten quy tac": "TEN_QUY_TAC",
    "tên quy tắc": "TEN_QUY_TAC",
    "ten rule": "TEN_QUY_TAC",
    "rule name": "TEN_QUY_TAC",

    "ket_qua": "KET_QUA",
    "ket qua": "KET_QUA",
    "kết quả": "KET_QUA",
    "kết quả chi trả": "KET_QUA",
    "trang thai chi tra": "KET_QUA",
    "trạng thái chi trả": "KET_QUA",

    "can_cu": "CAN_CU",
    "can cu": "CAN_CU",
    "căn cứ": "CAN_CU",
    "can cu phap ly": "CAN_CU",
    "căn cứ pháp lý": "CAN_CU",
    "căn cứ pháp lý / nghiệp vụ": "CAN_CU",
    "căn cứ nghiệp vụ": "CAN_CU",
}

# Schema người dùng nhìn thấy. Các khóa kỹ thuật trong DB vẫn được backend quản lý.
SCHEMA_FIELDS = {
    "NHAN_VIEN_KHONG_KET_QUA": [
        {"field": "MA_NHAN_VIEN", "label": "Mã nhân viên (MSNV)", "required": True},
        {"field": "HO_TEN", "label": "Họ và tên", "required": True},
        {"field": "TEN_DON_VI", "label": "Đơn vị công tác", "required": True},
        {"field": "CHUC_VU", "label": "Chức vụ / Vị trí", "required": False},
        {"field": "EMAIL", "label": "Email", "required": False},
        {"field": "EXTENSION", "label": "Máy lẻ / Extension", "required": False},
        {"field": "IGNORE", "label": "-- Bỏ qua trường này --", "required": False},
    ],
    "NHAN_VIEN_CO_KET_QUA": [
        {"field": "MA_NHAN_VIEN", "label": "Mã nhân viên (MSNV)", "required": True},
        {"field": "KET_QUA", "label": "Kết quả chi trả (YES/NO)", "required": True},
        {"field": "CAN_CU", "label": "Căn cứ pháp lý / nghiệp vụ", "required": True},
        {"field": "IGNORE", "label": "-- Bỏ qua trường này --", "required": False},
    ],
    "DON_VI": [
        {"field": "TEN_DON_VI", "label": "Tên đơn vị", "required": True},
        {"field": "IGNORE", "label": "-- Bỏ qua trường này --", "required": False},
    ],
    "BUSINESS_RULE": [
        {"field": "MA_QUY_TAC", "label": "Mã quy tắc", "required": False},
        {"field": "TEN_QUY_TAC", "label": "Tên quy tắc", "required": True},
        {"field": "TEN_DON_VI", "label": "Tên đơn vị áp dụng", "required": True},
        {"field": "KET_QUA", "label": "Kết quả (YES/NO)", "required": True},
        {"field": "CAN_CU", "label": "Căn cứ pháp lý / nghiệp vụ", "required": True},
        {"field": "IGNORE", "label": "-- Bỏ qua trường này --", "required": False},
    ],
}

REQUIRED_BY_DATA_TYPE = {
    "NHAN_VIEN_KHONG_KET_QUA": ["MA_NHAN_VIEN", "HO_TEN", "TEN_DON_VI"],
    "NHAN_VIEN_CO_KET_QUA": ["MA_NHAN_VIEN", "KET_QUA", "CAN_CU"],
    "DON_VI": ["TEN_DON_VI"],
    "BUSINESS_RULE": ["TEN_QUY_TAC", "TEN_DON_VI", "KET_QUA", "CAN_CU"],
}


class MappingService:
    def __init__(self):
        self.mapper = GD202SchemaMappingAdapter()

    @staticmethod
    def _mapping_schema_mo_rong(
        headers: List[str],
        sample_rows: List[Dict[str, Any]],
        data_type: str,
    ) -> List[Dict[str, Any]]:
        items = []
        allowed = {item["field"] for item in SCHEMA_FIELDS[data_type]}

        for header in headers:
            key = str(header).strip().lower()
            target = EXTRA_HEADER_ALIASES.get(key)
            if target not in allowed:
                target = "IGNORE"

            sample = ""
            if sample_rows:
                sample = str(sample_rows[0].get(header, "") or "")
            if len(sample) > 40:
                sample = sample[:37] + "..."

            accepted = target != "IGNORE"
            confidence = 1.0 if accepted else 0.0
            items.append({
                "source_column": header,
                "target_field": target,
                "confidence": round(confidence * 100.0, 1),
                "confidence_ratio": confidence,
                "confidence_level": "HIGH" if accepted else "VERY_LOW",
                "confidence_label": "Cao" if accepted else "Rất thấp",
                "sample_value": sample,
                "status": "VALID" if accepted else "UNKNOWN",
                "status_text": "Hợp lệ" if accepted else "Chưa xác định",
                "source_type": "schema_alias" if accepted else "unknown",
                "requires_confirmation": False,
                "confirmed_by_user": False,
                "is_edited": False,
                "accepted": accepted,
            })
        return items

    @staticmethod
    def _confidence_level(ratio: float) -> tuple[str, str]:
        if ratio >= 0.85:
            return "HIGH", "Cao"
        if ratio >= 0.60:
            return "MEDIUM", "Trung bình"
        if ratio >= 0.40:
            return "LOW", "Thấp"
        return "VERY_LOW", "Rất thấp"

    @staticmethod
    def _sample_value(rows: List[Dict[str, Any]], source: str) -> str:
        if not rows:
            return ""
        value = str(rows[0].get(source, "") or "")
        return value if len(value) <= 40 else value[:37] + "..."

    def _to_ui_item(
        self,
        source: str,
        target: str | None,
        confidence: float,
        sample_rows: List[Dict[str, Any]],
        source_method: str = "mapping",
        requires_confirmation: bool | None = None,
        raw_value: Any = None,
        allowed_fields: set[str] | None = None,
    ) -> Dict[str, Any]:
        ratio = max(0.0, min(1.0, float(confidence or 0.0)))
        ui_target = TARGET_TO_UI.get(str(target)) if target else None
        if allowed_fields is not None and ui_target not in allowed_fields:
            ui_target = None
        accepted = ui_target is not None
        ui_target = ui_target or "IGNORE"
        needs_confirmation = (
            ratio < CONFIRMATION_THRESHOLD
            if requires_confirmation is None
            else bool(requires_confirmation)
        )
        if ui_target == "IGNORE":
            needs_confirmation = False
        level, label = self._confidence_level(ratio)

        if ui_target == "IGNORE":
            status, status_text = "UNKNOWN", "Chưa xác định"
        elif needs_confirmation:
            status, status_text = "NEEDS_CONFIRMATION", "Cần xác nhận"
        else:
            status, status_text = "VALID", "Hợp lệ"

        sample = self._sample_value(sample_rows, source)
        if not sample and raw_value not in (None, ""):
            sample = str(raw_value)

        return {
            "source_column": source,
            "target_field": ui_target,
            "confidence": round(ratio * 100.0, 1),
            "confidence_ratio": round(ratio, 4),
            "confidence_level": level,
            "confidence_label": label,
            "sample_value": sample,
            "status": status,
            "status_text": status_text,
            "source_type": source_method,
            "requires_confirmation": bool(needs_confirmation),
            "confirmed_by_user": False,
            "is_edited": False,
            "accepted": accepted,
        }

    def generate_mapping(
        self,
        headers: List[str],
        sample_rows: List[Dict[str, Any]],
        data_type: str = "NHAN_VIEN_KHONG_KET_QUA",
    ) -> Dict[str, Any]:
        if data_type not in SCHEMA_FIELDS:
            data_type = "NHAN_VIEN_KHONG_KET_QUA"

        if data_type != "NHAN_VIEN_KHONG_KET_QUA":
            return self._result(
                data_type,
                self._mapping_schema_mo_rong(headers, sample_rows, data_type),
            )

        allowed = {item["field"] for item in SCHEMA_FIELDS[data_type]}
        candidates = self.mapper.map_headers([str(header) for header in headers])
        items = [
            self._to_ui_item(
                source=item.source,
                target=item.target,
                confidence=item.confidence,
                sample_rows=sample_rows,
                source_method=item.source_method,
                requires_confirmation=item.requires_confirmation,
                raw_value=item.raw_value,
                allowed_fields=allowed,
            )
            for item in candidates
        ]
        return self._result(data_type, items)

    def generate_from_pipeline(
        self,
        pipeline_payload: Dict[str, Any],
        headers: List[str],
        sample_rows: List[Dict[str, Any]],
        data_type: str = "NHAN_VIEN_KHONG_KET_QUA",
    ) -> Dict[str, Any]:
        if data_type not in SCHEMA_FIELDS:
            data_type = "NHAN_VIEN_KHONG_KET_QUA"
        if data_type != "NHAN_VIEN_KHONG_KET_QUA":
            return self.generate_mapping(headers, sample_rows, data_type)

        allowed = {item["field"] for item in SCHEMA_FIELDS[data_type]}
        records = list(pipeline_payload.get("records") or [])
        source_type = str((pipeline_payload.get("metadata") or {}).get("source_type") or "")
        items: List[Dict[str, Any]] = []

        if source_type == "structured" and records:
            for mapping in records[0].get("mappings") or []:
                items.append(
                    self._to_ui_item(
                        source=str(mapping.get("source") or ""),
                        target=mapping.get("target"),
                        confidence=float(mapping.get("confidence") or 0.0),
                        sample_rows=sample_rows,
                        source_method=str(mapping.get("source_method") or "mapping"),
                        requires_confirmation=bool(mapping.get("requires_confirmation")),
                        raw_value=mapping.get("raw_value"),
                        allowed_fields=allowed,
                    )
                )
        else:
            source_by_target = {
                "Mã nhân viên": "ma_nhan_vien",
                "Họ tên": "ho_ten",
                "Đơn vị": "don_vi",
                "Chức vụ": "chuc_vu",
                "Email": "email",
                "Extension": "extension",
            }
            for source in headers:
                target = source_by_target.get(source)
                if not target:
                    continue
                scores, methods = [], []
                raw_value = None
                requires = False
                for record in records:
                    confidence = record.get("confidence") or {}
                    if target in confidence:
                        scores.append(float(confidence[target]))
                    for mapping in record.get("mappings") or []:
                        if mapping.get("target") == target:
                            methods.append(str(mapping.get("source_method") or "information_extraction"))
                            requires = requires or bool(mapping.get("requires_confirmation"))
                            raw_value = raw_value or mapping.get("raw_value")
                ratio = min(scores) if scores else 0.0
                items.append(
                    self._to_ui_item(
                        source=source,
                        target=target,
                        confidence=ratio,
                        sample_rows=sample_rows,
                        source_method=methods[0] if methods else "information_extraction",
                        requires_confirmation=requires or ratio < CONFIRMATION_THRESHOLD,
                        raw_value=raw_value,
                        allowed_fields=allowed,
                    )
                )

        existing_sources = {item["source_column"] for item in items}
        for header in headers:
            if header not in existing_sources:
                items.append(self._to_ui_item(
                    header, None, 0.0, sample_rows,
                    source_method="unknown", allowed_fields=allowed,
                ))
        return self._result(data_type, items)

    def _result(self, data_type: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "data_type": data_type,
            "mapping_items": items,
            "schema_options": SCHEMA_FIELDS[data_type],
            "duplicates": self.find_duplicate_mappings(items),
            "missing_fields": self.find_missing_required(items, data_type),
            "pending_confirmation": self.find_pending_confirmation(items),
        }

    @staticmethod
    def find_duplicate_mappings(mapping_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[str]] = {}
        for item in mapping_items:
            target = str(item.get("target_field") or "")
            if target and target not in {"IGNORE", "OTHER"}:
                grouped.setdefault(target, []).append(str(item.get("source_column") or ""))
        return [
            {
                "target_field": target,
                "columns": columns,
                "message": f"Các cột [{', '.join(columns)}] cùng ánh xạ vào '{target}'.",
            }
            for target, columns in grouped.items()
            if len(columns) > 1
        ]

    @staticmethod
    def find_missing_required(mapping_items: List[Dict[str, Any]], data_type: str) -> List[str]:
        required = REQUIRED_BY_DATA_TYPE.get(data_type, REQUIRED_BY_DATA_TYPE["NHAN_VIEN_KHONG_KET_QUA"])
        mapped = {
            str(item.get("target_field"))
            for item in mapping_items
            if item.get("target_field") not in {None, "", "IGNORE", "OTHER"}
        }
        return [field for field in required if field not in mapped]

    @staticmethod
    def find_pending_confirmation(mapping_items: List[Dict[str, Any]]) -> List[str]:
        pending = []
        for item in mapping_items:
            target = item.get("target_field")
            if target in {None, "", "IGNORE", "OTHER"}:
                continue
            ratio = float(item.get("confidence_ratio") or 0.0)
            if not ratio and item.get("confidence") is not None:
                value = float(item.get("confidence") or 0.0)
                ratio = value / 100.0 if value > 1 else value
            needs = bool(item.get("requires_confirmation")) or ratio < CONFIRMATION_THRESHOLD
            confirmed = bool(item.get("confirmed_by_user")) or bool(item.get("is_edited"))
            if needs and not confirmed:
                pending.append(str(item.get("source_column") or target))
        return pending
