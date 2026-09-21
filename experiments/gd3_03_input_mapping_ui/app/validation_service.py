from __future__ import annotations

import re
from typing import Any, Dict, List

from experiments.gd2_04_backend_upload_ui.app.normalization import (
    chuan_hoa_ho_ten,
    chuan_hoa_ket_qua,
    chuan_hoa_msnv,
    chuan_hoa_ten_don_vi,
)
from experiments.gd3_02_information_mapping.src.constants import CONFIRMATION_THRESHOLD

from .mapping_service import REQUIRED_BY_DATA_TYPE, MappingService


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MSNV_RE = re.compile(r"^[A-Za-z]{2,6}\d{2,8}$")


class ValidationService:
    """Validation UI sau khi người dùng xem/sửa mapping.

    GĐ3-02 chịu trách nhiệm extraction/schema validation ban đầu. Lớp này kiểm tra
    mapping cuối cùng mà người dùng chuẩn bị Commit và bắt buộc Human Confirmation
    đối với confidence < 0.85.
    """

    def __init__(self):
        self.mapping_service = MappingService()

    @staticmethod
    def _ratio(item: Dict[str, Any]) -> float:
        if item.get("confidence_ratio") is not None:
            value = float(item.get("confidence_ratio") or 0.0)
        else:
            value = float(item.get("confidence") or 0.0)
            if value > 1:
                value /= 100.0
        return max(0.0, min(1.0, value))

    def validate_dataset(
        self,
        rows: List[Dict[str, Any]],
        mapping_items: List[Dict[str, Any]],
        data_type: str,
    ) -> Dict[str, Any]:
        data_type = str(
            data_type or "NHAN_VIEN_KHONG_KET_QUA"
        ).strip().upper()

        if data_type not in REQUIRED_BY_DATA_TYPE:
            return {
                "status": "FAIL",
                "can_commit": False,
                "error_count": 1,
                "warning_count": 0,
                "errors": [{
                    "field": "data_type",
                    "row_idx": 0,
                    "message": (
                        f"Loại dữ liệu không hỗ trợ: {data_type}"
                    ),
                    "type": "UNSUPPORTED_DATA_TYPE",
                }],
                "warnings": [],
                "summary": {
                    "total_records": len(rows),
                    "total_fields": len(mapping_items),
                    "valid_records": 0,
                    "invalid_records": len(rows),
                    "pending_confirmation": 0,
                },
                "checklist": [],
            }

        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        target_to_source: Dict[str, str] = {}
        source_counts: Dict[str, List[str]] = {}

        for item in mapping_items:
            src = str(item.get("source_column") or "").strip()
            tgt = str(item.get("target_field") or "").strip()
            if not src:
                continue

            if tgt and tgt not in {"IGNORE", "OTHER"}:
                source_counts.setdefault(tgt, []).append(src)
                target_to_source[tgt] = src

                ratio = self._ratio(item)
                needs_confirmation = bool(item.get("requires_confirmation")) or ratio < CONFIRMATION_THRESHOLD
                confirmed = bool(item.get("confirmed_by_user")) or bool(item.get("is_edited"))
                if needs_confirmation and not confirmed:
                    errors.append({
                        "field": src,
                        "row_idx": 0,
                        "message": (
                            f"Mapping '{src}' có confidence {ratio * 100:.1f}% (<85%). "
                            "Phải xác nhận hoặc chỉnh sửa trước khi Commit."
                        ),
                        "type": "LOW_CONFIDENCE_UNCONFIRMED",
                    })
                elif needs_confirmation and confirmed:
                    warnings.append({
                        "field": src,
                        "row_idx": 0,
                        "message": f"Mapping confidence thấp '{src}' đã được người dùng xác nhận.",
                        "type": "LOW_CONFIDENCE_CONFIRMED",
                    })
            else:
                warnings.append({
                    "field": src,
                    "row_idx": 0,
                    "message": f"Cột '{src}' đang được bỏ qua/chưa xác định.",
                    "type": "UNKNOWN_FIELD",
                })

        duplicates = self.mapping_service.find_duplicate_mappings(mapping_items)
        for duplicate in duplicates:
            errors.append({
                "field": duplicate["target_field"],
                "row_idx": 0,
                "message": duplicate["message"],
                "type": "DUPLICATE_MAPPING",
            })

        required = REQUIRED_BY_DATA_TYPE[data_type]
        missing_required = [field for field in required if field not in target_to_source]
        for field in missing_required:
            errors.append({
                "field": field,
                "row_idx": 0,
                "message": f"Thiếu trường bắt buộc '{field}'.",
                "type": "MISSING_REQUIRED",
            })

        valid_rows = 0
        invalid_rows = 0

        for row_idx, row in enumerate(rows, start=1):
            before = len(errors)

            # =====================================================
            # NHÂN VIÊN
            # =====================================================
            if data_type.startswith("NHAN_VIEN"):
                msnv_col = target_to_source.get(
                    "MA_NHAN_VIEN"
                )
                name_col = target_to_source.get(
                    "HO_TEN"
                )
                unit_col = target_to_source.get(
                    "TEN_DON_VI"
                )
                email_col = target_to_source.get(
                    "EMAIL"
                )
                extension_col = target_to_source.get(
                    "EXTENSION"
                )

                if msnv_col:
                    raw = str(
                        row.get(msnv_col) or ""
                    ).strip()

                    normalized = chuan_hoa_msnv(raw)

                    if not normalized:
                        errors.append({
                            "field": msnv_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                "Mã nhân viên không được để trống."
                            ),
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

                    elif not MSNV_RE.fullmatch(
                        normalized
                    ):
                        errors.append({
                            "field": msnv_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                f"Mã nhân viên '{raw}' "
                                "không đúng định dạng."
                            ),
                            "type": "INVALID_FORMAT",
                        })

                if name_col:
                    raw = str(
                        row.get(name_col) or ""
                    ).strip()

                    if not chuan_hoa_ho_ten(raw):
                        errors.append({
                            "field": name_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                "Họ tên không được để trống."
                            ),
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

                if unit_col:
                    raw = str(
                        row.get(unit_col) or ""
                    ).strip()

                    if not chuan_hoa_ten_don_vi(raw):
                        errors.append({
                            "field": unit_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                "Đơn vị không được để trống."
                            ),
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

                if email_col:
                    raw = str(
                        row.get(email_col) or ""
                    ).strip()

                    if raw and not EMAIL_RE.fullmatch(raw):
                        errors.append({
                            "field": email_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                f"Email '{raw}' không hợp lệ."
                            ),
                            "type": "INVALID_EMAIL",
                        })

                if extension_col:
                    raw = str(
                        row.get(extension_col) or ""
                    ).strip()

                    if (
                        raw
                        and not re.fullmatch(
                            r"\d{2,6}",
                            raw,
                        )
                    ):
                        errors.append({
                            "field": extension_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                f"Extension '{raw}' "
                                "phải gồm 2-6 chữ số."
                            ),
                            "type": "INVALID_EXTENSION",
                        })

                # Nhân viên có kết quả
                # = ngoại lệ cá nhân.
                if (
                    data_type
                    == "NHAN_VIEN_CO_KET_QUA"
                ):
                    result_col = (
                        target_to_source.get(
                            "KET_QUA"
                        )
                    )
                    basis_col = (
                        target_to_source.get(
                            "CAN_CU"
                        )
                    )

                    if result_col:
                        raw_result = str(
                            row.get(result_col)
                            or ""
                        ).strip()

                        normalized_result = (
                            chuan_hoa_ket_qua(
                                raw_result
                            )
                        )

                        if normalized_result not in {
                            "YES",
                            "NO",
                        }:
                            errors.append({
                                "field": result_col,
                                "row_idx": row_idx,
                                "message": (
                                    f"Dòng {row_idx}: "
                                    "Kết quả chỉ được "
                                    "YES hoặc NO."
                                ),
                                "type":
                                    "INVALID_SALARY_RESULT",
                            })

                    if basis_col:
                        basis = str(
                            row.get(basis_col)
                            or ""
                        ).strip()

                        if not basis:
                            errors.append({
                                "field": basis_col,
                                "row_idx": row_idx,
                                "message": (
                                    f"Dòng {row_idx}: "
                                    "Căn cứ không được "
                                    "để trống."
                                ),
                                "type":
                                    "EMPTY_REQUIRED_VALUE",
                            })

            # =====================================================
            # ĐƠN VỊ
            # =====================================================
            elif data_type == "DON_VI":
                unit_col = target_to_source.get(
                    "TEN_DON_VI"
                )

                if unit_col:
                    raw = str(
                        row.get(unit_col) or ""
                    ).strip()

                    if not chuan_hoa_ten_don_vi(raw):
                        errors.append({
                            "field": unit_col,
                            "row_idx": row_idx,
                            "message": (
                                f"Dòng {row_idx}: "
                                "Tên đơn vị không được "
                                "để trống."
                            ),
                            "type":
                                "EMPTY_REQUIRED_VALUE",
                        })

            # =====================================================
            # BUSINESS RULE
            # =====================================================
            elif data_type == "BUSINESS_RULE":
                result_col = target_to_source.get("KET_QUA")
                basis_col = target_to_source.get("CAN_CU")
                unit_col = target_to_source.get("TEN_DON_VI")
                name_col = target_to_source.get("TEN_QUY_TAC")

                if name_col:
                    rule_name = str(row.get(name_col) or "").strip()
                    if not rule_name:
                        errors.append({
                            "field": name_col,
                            "row_idx": row_idx,
                            "message": f"Dòng {row_idx}: Tên quy tắc không được để trống.",
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

                if unit_col:
                    unit_value = str(row.get(unit_col) or "").strip()
                    if not chuan_hoa_ten_don_vi(unit_value):
                        errors.append({
                            "field": unit_col,
                            "row_idx": row_idx,
                            "message": f"Dòng {row_idx}: Tên đơn vị áp dụng không được để trống.",
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

                if result_col:
                    raw_result = str(row.get(result_col) or "").strip()
                    normalized_result = chuan_hoa_ket_qua(raw_result)
                    if normalized_result not in {"YES", "NO"}:
                        errors.append({
                            "field": result_col,
                            "row_idx": row_idx,
                            "message": f"Dòng {row_idx}: Kết quả quy tắc phải là YES hoặc NO.",
                            "type": "INVALID_RULE_RESULT",
                        })

                if basis_col:
                    basis = str(row.get(basis_col) or "").strip()
                    if not basis:
                        errors.append({
                            "field": basis_col,
                            "row_idx": row_idx,
                            "message": f"Dòng {row_idx}: Căn cứ quy tắc không được để trống.",
                            "type": "EMPTY_REQUIRED_VALUE",
                        })

            if len(errors) == before:
                valid_rows += 1
            else:
                invalid_rows += 1

        has_pending_confirmation = any(e["type"] == "LOW_CONFIDENCE_UNCONFIRMED" for e in errors)
        is_pass = bool(rows) and not errors and invalid_rows == 0

        checklist = [
            {
                "name": "Cấu trúc Schema",
                "passed": not missing_required,
                "detail": "Đủ trường bắt buộc" if not missing_required else f"Thiếu: {', '.join(missing_required)}",
            },
            {
                "name": "Trùng lặp Mapping",
                "passed": not duplicates,
                "detail": "Không có mapping trùng" if not duplicates else "Cần sửa mapping trùng",
            },
            {
                "name": "Human Confirmation (<85%)",
                "passed": not has_pending_confirmation,
                "detail": "Không còn mapping confidence thấp chưa xác nhận" if not has_pending_confirmation else "Có mapping phải xác nhận/sửa",
            },
            {
                "name": "Định dạng dữ liệu",
                "passed": invalid_rows == 0,
                "detail": f"{valid_rows}/{len(rows)} bản ghi hợp lệ",
            },
            {
                "name": "Độc lập nghiệp vụ",
                "passed": True,
                "detail": "Validation không quyết định YES/NO/CHUA_XAC_DINH",
            },
        ]

        return {
            "status": "PASS" if is_pass else "FAIL",
            "can_commit": is_pass,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:100],
            "warnings": warnings[:100],
            "summary": {
                "total_records": len(rows),
                "total_fields": len(mapping_items),
                "valid_records": valid_rows,
                "invalid_records": invalid_rows,
                "pending_confirmation": sum(1 for e in errors if e["type"] == "LOW_CONFIDENCE_UNCONFIRMED"),
            },
            "checklist": checklist,
        }
