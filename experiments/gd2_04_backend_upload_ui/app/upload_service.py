from __future__ import annotations
import json
import sqlite3
from typing import Any, Dict, List, Tuple

from .database import ensure_unit
from .integration.file_reader_bridge import read_file
from .integration.schema_mapping_bridge import SchemaMappingBridge
from .normalization import (
    chuan_hoa_ho_ten,
    chuan_hoa_ho_ten_chuan,
    chuan_hoa_ket_qua,
    chuan_hoa_msnv,
    chuan_hoa_ten_don_vi,
    chuan_hoa_unicode,
)

DATA_TYPES = {"NHAN_VIEN_KHONG_KET_QUA", "NHAN_VIEN_CO_KET_QUA", "DON_VI", "BUSINESS_RULE"}
MODES = {"APPEND", "UPSERT", "REPLACE"}
REQUIRED_FIELDS = {
    "NHAN_VIEN_KHONG_KET_QUA": ["MA_NHAN_VIEN", "HO_TEN"],
    "NHAN_VIEN_CO_KET_QUA": ["MA_NHAN_VIEN", "HO_TEN", "KET_QUA", "CAN_CU"],
    "DON_VI": ["TEN_DON_VI"],
    "BUSINESS_RULE": ["KET_QUA", "CAN_CU"],
}


def _validate_schema(data_type: str, mapped: Dict[str, str]) -> Tuple[bool, List[str], List[str]]:
    missing = [x for x in REQUIRED_FIELDS[data_type] if x not in mapped]
    if data_type == "BUSINESS_RULE" and "TEN_DON_VI" not in mapped and "LOAI_DON_VI" not in mapped:
        missing.append("TEN_DON_VI hoặc LOAI_DON_VI")
    warnings = [f"Thiếu trường bắt buộc: {x}" for x in missing]
    return not missing, missing, warnings


def preview_upload(content: bytes, filename: str, data_type: str) -> Dict[str, Any]:
    if data_type not in DATA_TYPES:
        raise ValueError(f"Loại dữ liệu không hợp lệ: {data_type}")
    headers, rows, metadata = read_file(content, filename)
    if not headers:
        raise ValueError("Không đọc được header từ file.")
    mapper = SchemaMappingBridge()
    mapped, details = mapper.detect_mapping(headers)
    valid_schema, missing, warnings = _validate_schema(data_type, mapped)
    low = [d for d in details if not d.get("accepted") or float(d.get("confidence") or 0) < 0.70]
    if low:
        warnings.append("Có cột confidence thấp/chưa xác định: " + ", ".join(str(x.get("original_text")) for x in low))

    valid_rows = 0
    invalid_rows = 0
    for row in rows:
        if data_type.startswith("NHAN_VIEN"):
            ok = bool(row.get(mapped.get("MA_NHAN_VIEN", "")) and row.get(mapped.get("HO_TEN", "")))
            if data_type == "NHAN_VIEN_CO_KET_QUA":
                ok = ok and bool(row.get(mapped.get("KET_QUA", "")) and row.get(mapped.get("CAN_CU", "")))
        elif data_type == "DON_VI":
            ok = bool(row.get(mapped.get("TEN_DON_VI", "")))
        else:
            ok = bool(row.get(mapped.get("KET_QUA", "")) and row.get(mapped.get("CAN_CU", "")))
            ok = ok and bool(row.get(mapped.get("TEN_DON_VI", "")) or row.get(mapped.get("LOAI_DON_VI", "")))
        valid_rows += int(ok)
        invalid_rows += int(not ok)

    return {
        "ok": True,
        "filename": filename,
        "data_type": data_type,
        "so_dong_doc": len(rows),
        "headers": headers,
        "mapping": details,
        "mapped_columns": mapped,
        "low_confidence_columns": low,
        "missing_fields": missing,
        "warnings": warnings,
        "preview_rows": rows[:5],
        "valid_rows_count": valid_rows,
        "invalid_rows_count": invalid_rows,
        "can_commit": valid_schema,
        "metadata": metadata,
    }


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_bool_int(value: Any, default: int = 1) -> int:
    if value is None or str(value).strip() == "":
        return default
    norm = str(value).strip().lower()
    if norm in {"1", "true", "yes", "y", "co", "có"}:
        return 1
    if norm in {"0", "false", "no", "n", "khong", "không"}:
        return 0
    return default


def commit_upload(conn: sqlite3.Connection, content: bytes, filename: str, data_type: str, mode: str = "APPEND") -> Dict[str, Any]:
    mode = mode.upper()
    if data_type not in DATA_TYPES:
        raise ValueError(f"Loại dữ liệu không hợp lệ: {data_type}")
    if mode not in MODES:
        raise ValueError(f"Chế độ không hợp lệ: {mode}")

    headers, rows, metadata = read_file(content, filename)
    mapper = SchemaMappingBridge()
    mapped, details = mapper.detect_mapping(headers)
    valid_schema, missing, _ = _validate_schema(data_type, mapped)
    if not valid_schema:
        return {"ok": False, "message": "Thiếu trường bắt buộc", "missing_fields": missing, "so_dong_import": 0, "mapping": details}

    imported = skipped = errors = 0
    cur = conn.cursor()
    try:
        cur.execute("BEGIN TRANSACTION")

        if data_type in {"NHAN_VIEN_KHONG_KET_QUA", "NHAN_VIEN_CO_KET_QUA"} and mode == "REPLACE":
            cur.execute("DELETE FROM ngoai_le_ca_nhan")
            cur.execute("DELETE FROM nhan_vien")
        elif data_type == "DON_VI" and mode == "REPLACE":
            cur.execute("DELETE FROM don_vi_nguon")
        elif data_type == "BUSINESS_RULE" and mode == "REPLACE":
            cur.execute("DELETE FROM business_rule")

        for idx, row in enumerate(rows, 1):
            try:
                if data_type.startswith("NHAN_VIEN"):
                    ma = chuan_hoa_msnv(row.get(mapped["MA_NHAN_VIEN"]))
                    ho_ten = chuan_hoa_ho_ten(row.get(mapped["HO_TEN"]))
                    if not ma or not ho_ten:
                        errors += 1
                        continue
                    unit_name = chuan_hoa_ten_don_vi(row.get(mapped.get("TEN_DON_VI", ""))) if mapped.get("TEN_DON_VI") else ""
                    ma_don_vi = ensure_unit(conn, unit_name) if unit_name else None
                    chuc_vu = chuan_hoa_unicode(row.get(mapped.get("CHUC_VU", ""))) if mapped.get("CHUC_VU") else None
                    email = chuan_hoa_unicode(row.get(mapped.get("EMAIL", ""))) if mapped.get("EMAIL") else None
                    existing = cur.execute("SELECT id FROM nhan_vien WHERE ma_nhan_vien=?", (ma,)).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    cur.execute(
                        """INSERT INTO nhan_vien(ma_nhan_vien,ho_ten,ho_ten_chuan,ma_don_vi,ten_don_vi,don_vi,chuc_vu,email)
                           VALUES(?,?,?,?,?,?,?,?)
                           ON CONFLICT(ma_nhan_vien) DO UPDATE SET
                           ho_ten=excluded.ho_ten,ho_ten_chuan=excluded.ho_ten_chuan,ma_don_vi=excluded.ma_don_vi,
                           ten_don_vi=excluded.ten_don_vi,don_vi=excluded.don_vi,chuc_vu=excluded.chuc_vu,email=excluded.email""",
                        (ma, ho_ten, chuan_hoa_ho_ten_chuan(ho_ten), ma_don_vi, unit_name or None, unit_name or None, chuc_vu or None, email or None),
                    )
                    if data_type == "NHAN_VIEN_CO_KET_QUA":
                        result = chuan_hoa_ket_qua(row.get(mapped["KET_QUA"]))
                        can_cu = chuan_hoa_unicode(row.get(mapped["CAN_CU"]))
                        if result not in {"YES", "NO"} or not can_cu:
                            raise ValueError(f"Dòng {idx}: ket_qua/can_cu không hợp lệ")
                        if mode != "APPEND":
                            cur.execute("DELETE FROM ngoai_le_ca_nhan WHERE ma_nhan_vien=?", (ma,))
                        cur.execute(
                            """INSERT INTO ngoai_le_ca_nhan(ma_quy_tac,ma_nhan_vien,ket_qua,can_cu,muc_uu_tien,ngay_hieu_luc,ngay_het_hieu_luc,dang_ap_dung,la_mock,ghi_chu)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (
                                f"EX_{ma}", ma, result, can_cu,
                                _to_int(row.get(mapped.get("MUC_UU_TIEN", "")), 100),
                                chuan_hoa_unicode(row.get(mapped.get("NGAY_HIEU_LUC", ""))) or None if mapped.get("NGAY_HIEU_LUC") else None,
                                chuan_hoa_unicode(row.get(mapped.get("NGAY_HET_HIEU_LUC", ""))) or None if mapped.get("NGAY_HET_HIEU_LUC") else None,
                                _to_bool_int(row.get(mapped.get("DANG_AP_DUNG", "")), 1) if mapped.get("DANG_AP_DUNG") else 1,
                                _to_bool_int(row.get(mapped.get("LA_MOCK", "")), 0) if mapped.get("LA_MOCK") else 0,
                                chuan_hoa_unicode(row.get(mapped.get("GHI_CHU", ""))) or None if mapped.get("GHI_CHU") else None,
                            ),
                        )
                    imported += 1

                elif data_type == "DON_VI":
                    ten = chuan_hoa_ten_don_vi(row.get(mapped["TEN_DON_VI"]))
                    if not ten:
                        errors += 1
                        continue
                    loai = chuan_hoa_unicode(row.get(mapped.get("LOAI_DON_VI", ""))) if mapped.get("LOAI_DON_VI") else None
                    ma_noi_bo = ensure_unit(conn, ten, loai)
                    ma_nguon = chuan_hoa_unicode(row.get(mapped.get("MA_DON_VI_NGUON", ""))) if mapped.get("MA_DON_VI_NGUON") else None
                    cha = chuan_hoa_ten_don_vi(row.get(mapped.get("DON_VI_CHA", ""))) if mapped.get("DON_VI_CHA") else None
                    existing = cur.execute("SELECT id FROM don_vi_nguon WHERE ten_don_vi=?", (ten,)).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    if existing:
                        cur.execute("UPDATE don_vi_nguon SET ma_don_vi_nguon=?,loai_don_vi=?,don_vi_cha=? WHERE id=?", (ma_nguon or ma_noi_bo, loai or None, cha or None, existing["id"]))
                    else:
                        cur.execute("INSERT INTO don_vi_nguon(ma_don_vi_nguon,ten_don_vi,loai_don_vi,don_vi_cha) VALUES(?,?,?,?)", (ma_nguon or ma_noi_bo, ten, loai or None, cha or None))
                    imported += 1

                else:  # BUSINESS_RULE
                    result = chuan_hoa_ket_qua(row.get(mapped["KET_QUA"]))
                    can_cu = chuan_hoa_unicode(row.get(mapped["CAN_CU"]))
                    ten_don_vi = chuan_hoa_ten_don_vi(row.get(mapped.get("TEN_DON_VI", ""))) if mapped.get("TEN_DON_VI") else ""
                    loai_don_vi = chuan_hoa_unicode(row.get(mapped.get("LOAI_DON_VI", ""))) if mapped.get("LOAI_DON_VI") else ""
                    if result not in {"YES", "NO"} or not can_cu or (not ten_don_vi and not loai_don_vi):
                        errors += 1
                        continue
                    ma_don_vi = ensure_unit(conn, ten_don_vi, loai_don_vi or None) if ten_don_vi else None
                    pham_vi = "DON_VI" if ten_don_vi else "LOAI_DON_VI"
                    ma_qt = chuan_hoa_unicode(row.get(mapped.get("MA_QUY_TAC", ""))) if mapped.get("MA_QUY_TAC") else ""
                    if not ma_qt:
                        ma_qt = f"BR_{idx:05d}"
                    existing = cur.execute("SELECT id FROM business_rule WHERE ma_quy_tac=?", (ma_qt,)).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    values = (
                        ma_qt,
                        chuan_hoa_unicode(row.get(mapped.get("TEN_QUY_TAC", ""))) or f"Quy tắc {ma_qt}" if mapped.get("TEN_QUY_TAC") else f"Quy tắc {ma_qt}",
                        pham_vi, ma_don_vi, ten_don_vi or None, loai_don_vi or None, result, can_cu,
                        _to_int(row.get(mapped.get("MUC_UU_TIEN", "")), 0) if mapped.get("MUC_UU_TIEN") else 0,
                        chuan_hoa_unicode(row.get(mapped.get("NGAY_HIEU_LUC", ""))) or None if mapped.get("NGAY_HIEU_LUC") else None,
                        chuan_hoa_unicode(row.get(mapped.get("NGAY_HET_HIEU_LUC", ""))) or None if mapped.get("NGAY_HET_HIEU_LUC") else None,
                        _to_bool_int(row.get(mapped.get("DANG_AP_DUNG", "")), 1) if mapped.get("DANG_AP_DUNG") else 1,
                        _to_bool_int(row.get(mapped.get("LA_MOCK", "")), 0) if mapped.get("LA_MOCK") else 0,
                        chuan_hoa_unicode(row.get(mapped.get("GHI_CHU", ""))) or None if mapped.get("GHI_CHU") else None,
                    )
                    cur.execute(
                        """INSERT INTO business_rule(ma_quy_tac,ten_quy_tac,pham_vi,ma_don_vi,ten_don_vi,loai_don_vi,ket_qua,can_cu,muc_uu_tien,ngay_hieu_luc,ngay_het_hieu_luc,dang_ap_dung,la_mock,ghi_chu)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(ma_quy_tac) DO UPDATE SET ten_quy_tac=excluded.ten_quy_tac,pham_vi=excluded.pham_vi,
                           ma_don_vi=excluded.ma_don_vi,ten_don_vi=excluded.ten_don_vi,loai_don_vi=excluded.loai_don_vi,
                           ket_qua=excluded.ket_qua,can_cu=excluded.can_cu,muc_uu_tien=excluded.muc_uu_tien,
                           ngay_hieu_luc=excluded.ngay_hieu_luc,ngay_het_hieu_luc=excluded.ngay_het_hieu_luc,
                           dang_ap_dung=excluded.dang_ap_dung,la_mock=excluded.la_mock,ghi_chu=excluded.ghi_chu""",
                        values,
                    )
                    imported += 1
            except Exception:
                raise

        conn.commit()
        return {
            "ok": True,
            "data_type": data_type,
            "mode": mode,
            "so_dong_import": imported,
            "so_dong_trung": skipped,
            "so_dong_loi": errors,
            "mapping": details,
            "metadata": metadata,
        }
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Lỗi commit, đã rollback toàn bộ transaction: {exc}") from exc
