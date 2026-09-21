from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from experiments.gd2_04_backend_upload_ui.app.database import ensure_unit
from experiments.gd2_04_backend_upload_ui.app.normalization import (
    chuan_hoa_ho_ten,
    chuan_hoa_ho_ten_chuan,
    chuan_hoa_ket_qua,
    chuan_hoa_msnv,
    chuan_hoa_ten_don_vi,
    chuan_hoa_tim_kiem,
    chuan_hoa_unicode,
)


SUPPORTED_DATA_TYPES = {
    "NHAN_VIEN_KHONG_KET_QUA",
    "NHAN_VIEN_CO_KET_QUA",
    "DON_VI",
    "BUSINESS_RULE",
}
SUPPORTED_MODES = {"APPEND", "UPSERT", "REPLACE"}


class CommitService:
    """Commit dữ liệu đã qua Validation.

    Quyết định YES/NO chỉ được ghi ở ``business_rule`` hoặc
    ``ngoai_le_ca_nhan``; không ghi trực tiếp vào ``nhan_vien``.
    """

    @staticmethod
    def _target_map(mapping_items: List[Dict[str, Any]] | Dict[str, str]) -> Dict[str, str]:
        target_map: Dict[str, str] = {}
        if isinstance(mapping_items, list):
            for item in mapping_items:
                source = str(item.get("source_column") or "").strip()
                target = str(item.get("target_field") or "").strip()
                if source and target and target not in {"IGNORE", "OTHER"}:
                    target_map[target] = source
            return target_map
        if isinstance(mapping_items, dict):
            for target, source in mapping_items.items():
                target = str(target or "").strip()
                source = str(source or "").strip()
                if source and target and target not in {"IGNORE", "OTHER"}:
                    target_map[target] = source
            return target_map
        raise ValueError("mapping_items phải là list hoặc dict.")

    @staticmethod
    def _mock_flag(can_cu: str) -> int:
        return int(str(can_cu or "").strip().lower().startswith(("[mock]", "mock")))

    @staticmethod
    def commit_dataset(
        conn: sqlite3.Connection,
        rows: List[Dict[str, Any]],
        mapping_items: List[Dict[str, Any]] | Dict[str, str],
        data_type: str = "NHAN_VIEN_KHONG_KET_QUA",
        mode: str = "APPEND",
    ) -> Dict[str, Any]:
        data_type = str(data_type or "NHAN_VIEN_KHONG_KET_QUA").strip().upper()
        if data_type not in SUPPORTED_DATA_TYPES:
            raise ValueError(f"Loại dữ liệu chưa hỗ trợ commit: {data_type}")

        mode = str(mode or "APPEND").strip().upper()
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"Chế độ nạp không hợp lệ: {mode}")
        if not rows:
            raise ValueError("Không có dữ liệu để commit.")

        target_map = CommitService._target_map(mapping_items)
        required_by_type = {
            "NHAN_VIEN_KHONG_KET_QUA": {"MA_NHAN_VIEN", "HO_TEN", "TEN_DON_VI"},
            "NHAN_VIEN_CO_KET_QUA": {"MA_NHAN_VIEN", "KET_QUA", "CAN_CU"},
            "DON_VI": {"TEN_DON_VI"},
            "BUSINESS_RULE": {"TEN_QUY_TAC", "TEN_DON_VI", "KET_QUA", "CAN_CU"},
        }
        missing = sorted(required_by_type[data_type] - set(target_map))
        if missing:
            raise ValueError(f"Thiếu trường ánh xạ bắt buộc: {', '.join(missing)}")

        imported = 0
        skipped = 0
        cur = conn.cursor()

        try:
            cur.execute("BEGIN TRANSACTION")

            # ---------------------------------------------------------
            # HỒ SƠ NHÂN VIÊN
            # ---------------------------------------------------------
            if data_type == "NHAN_VIEN_KHONG_KET_QUA":
                if mode == "REPLACE":
                    exception_count = cur.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0]
                    if exception_count:
                        raise ValueError(
                            "Không thể REPLACE danh sách nhân viên khi đang có ngoại lệ cá nhân. "
                            "Hãy dùng UPSERT hoặc xử lý ngoại lệ trước."
                        )

                    # REPLACE phải đồng bộ cả tài khoản USER. Chỉ xóa account của
                    # nhân viên không còn trong file mới; account của nhân viên vẫn
                    # tồn tại được giữ nguyên để không reset mật khẩu. ADMIN không
                    # bị ảnh hưởng. Transaction đảm bảo rollback toàn bộ nếu commit lỗi.
                    incoming_codes = {
                        chuan_hoa_msnv(row.get(target_map["MA_NHAN_VIEN"]))
                        for row in rows
                    }
                    incoming_codes.discard("")
                    stale_user_ids = []
                    for account in cur.execute(
                        "SELECT id, ma_nhan_vien FROM users "
                        "WHERE role='USER' AND ma_nhan_vien IS NOT NULL"
                    ).fetchall():
                        account_code = chuan_hoa_msnv(account["ma_nhan_vien"])
                        if account_code not in incoming_codes:
                            stale_user_ids.append(int(account["id"]))

                    for user_id in stale_user_ids:
                        cur.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
                        cur.execute("DELETE FROM users WHERE id=?", (user_id,))

                    cur.execute("DELETE FROM nhan_vien")

                for row_index, row in enumerate(rows, start=1):
                    ma = chuan_hoa_msnv(row.get(target_map["MA_NHAN_VIEN"]))
                    ho_ten = chuan_hoa_ho_ten(row.get(target_map["HO_TEN"]))
                    don_vi = chuan_hoa_ten_don_vi(row.get(target_map["TEN_DON_VI"]))
                    if not ma or not ho_ten or not don_vi:
                        raise ValueError(f"Dòng {row_index}: thiếu mã nhân viên, họ tên hoặc đơn vị.")

                    existing = cur.execute(
                        """
                        SELECT id, ma_don_vi, ten_don_vi, don_vi, chuc_vu, email, thong_tin_mo_rong
                        FROM nhan_vien WHERE ma_nhan_vien=?
                        """,
                        (ma,),
                    ).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue

                    ma_don_vi = ensure_unit(conn, don_vi, None)

                    chuc_vu_col = target_map.get("CHUC_VU")
                    chuc_vu = chuan_hoa_unicode(row.get(chuc_vu_col)) if chuc_vu_col else None
                    if not chuc_vu and existing:
                        chuc_vu = existing["chuc_vu"]

                    email_col = target_map.get("EMAIL")
                    email = chuan_hoa_unicode(row.get(email_col)) if email_col else None
                    if not email and existing:
                        email = existing["email"]

                    extension_col = target_map.get("EXTENSION")
                    extension = chuan_hoa_unicode(row.get(extension_col)) if extension_col else None
                    if extension:
                        thong_tin_mo_rong = json.dumps({"extension": extension}, ensure_ascii=False)
                    elif existing:
                        thong_tin_mo_rong = existing["thong_tin_mo_rong"] or "{}"
                    else:
                        thong_tin_mo_rong = "{}"

                    cur.execute(
                        """
                        INSERT INTO nhan_vien(
                            ma_nhan_vien, ho_ten, ho_ten_chuan, ma_don_vi,
                            ten_don_vi, don_vi, chuc_vu, email, thong_tin_mo_rong
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(ma_nhan_vien) DO UPDATE SET
                            ho_ten=excluded.ho_ten,
                            ho_ten_chuan=excluded.ho_ten_chuan,
                            ma_don_vi=excluded.ma_don_vi,
                            ten_don_vi=excluded.ten_don_vi,
                            don_vi=excluded.don_vi,
                            chuc_vu=excluded.chuc_vu,
                            email=excluded.email,
                            thong_tin_mo_rong=excluded.thong_tin_mo_rong,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            ma,
                            ho_ten,
                            chuan_hoa_ho_ten_chuan(ho_ten),
                            ma_don_vi,
                            don_vi,
                            don_vi,
                            chuc_vu or None,
                            email or None,
                            thong_tin_mo_rong,
                        ),
                    )
                    imported += 1

            # ---------------------------------------------------------
            # NGOẠI LỆ CÁ NHÂN IMPORT THEO FILE
            # ---------------------------------------------------------
            elif data_type == "NHAN_VIEN_CO_KET_QUA":
                if mode == "REPLACE":
                    cur.execute("DELETE FROM ngoai_le_ca_nhan")

                for row_index, row in enumerate(rows, start=1):
                    ma = chuan_hoa_msnv(row.get(target_map["MA_NHAN_VIEN"]))
                    ket_qua = chuan_hoa_ket_qua(row.get(target_map["KET_QUA"]))
                    can_cu = chuan_hoa_unicode(row.get(target_map["CAN_CU"]))
                    if not ma:
                        raise ValueError(f"Dòng {row_index}: mã nhân viên không được để trống.")
                    if ket_qua not in {"YES", "NO"} or not can_cu:
                        raise ValueError(f"Dòng {row_index}: KET_QUA/CAN_CU không hợp lệ.")

                    employee = cur.execute(
                        "SELECT id FROM nhan_vien WHERE UPPER(ma_nhan_vien)=UPPER(?)",
                        (ma,),
                    ).fetchone()
                    if employee is None:
                        raise ValueError(
                            f"Dòng {row_index}: nhân viên {ma} chưa tồn tại. "
                            "Hãy nhập hồ sơ nhân viên trước khi tạo ngoại lệ."
                        )

                    ma_quy_tac = f"EX_{ma}"
                    existing = cur.execute(
                        "SELECT id FROM ngoai_le_ca_nhan WHERE ma_quy_tac=?",
                        (ma_quy_tac,),
                    ).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    if existing:
                        cur.execute("DELETE FROM ngoai_le_ca_nhan WHERE ma_quy_tac=?", (ma_quy_tac,))

                    cur.execute(
                        """
                        INSERT INTO ngoai_le_ca_nhan(
                            ma_quy_tac, ma_nhan_vien, ket_qua, can_cu,
                            muc_uu_tien, dang_ap_dung, la_mock
                        ) VALUES(?,?,?,?,100,1,?)
                        """,
                        (ma_quy_tac, ma, ket_qua, can_cu, CommitService._mock_flag(can_cu)),
                    )
                    imported += 1

            # ---------------------------------------------------------
            # ĐƠN VỊ: người dùng chỉ cần cung cấp TÊN ĐƠN VỊ.
            # Mã đơn vị là khóa nội bộ do hệ thống tự sinh/duy trì.
            # ---------------------------------------------------------
            elif data_type == "DON_VI":
                if mode == "REPLACE":
                    dependent_count = cur.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM nhan_vien WHERE ma_don_vi IS NOT NULL)
                            + (SELECT COUNT(*) FROM business_rule WHERE ma_don_vi IS NOT NULL)
                        """
                    ).fetchone()[0]
                    if dependent_count:
                        raise ValueError(
                            "Không thể REPLACE toàn bộ đơn vị khi đang có nhân viên/rule tham chiếu. "
                            "Hãy dùng UPSERT."
                        )
                    cur.execute("DELETE FROM don_vi")

                for row_index, row in enumerate(rows, start=1):
                    ten_don_vi = chuan_hoa_ten_don_vi(row.get(target_map["TEN_DON_VI"]))
                    if not ten_don_vi:
                        raise ValueError(f"Dòng {row_index}: TEN_DON_VI không được để trống.")
                    ten_chuan = chuan_hoa_tim_kiem(ten_don_vi)
                    existing = cur.execute(
                        "SELECT ma_don_vi FROM don_vi WHERE ten_don_vi_chuan=?",
                        (ten_chuan,),
                    ).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    ensure_unit(conn, ten_don_vi, None)
                    imported += 1

            # ---------------------------------------------------------
            # BUSINESS RULE: UI/source chỉ cần tên rule, đơn vị, YES/NO, căn cứ.
            # Các trường kỹ thuật legacy vẫn được điền nội bộ để tương thích DB/engine.
            # ---------------------------------------------------------
            elif data_type == "BUSINESS_RULE":
                if mode == "REPLACE":
                    cur.execute("DELETE FROM business_rule")

                for row_index, row in enumerate(rows, start=1):
                    ten_quy_tac = chuan_hoa_unicode(row.get(target_map["TEN_QUY_TAC"]))
                    ten_don_vi = chuan_hoa_ten_don_vi(row.get(target_map["TEN_DON_VI"]))
                    ket_qua = chuan_hoa_ket_qua(row.get(target_map["KET_QUA"]))
                    can_cu = chuan_hoa_unicode(row.get(target_map["CAN_CU"]))
                    if not ten_quy_tac:
                        raise ValueError(f"Dòng {row_index}: TEN_QUY_TAC không được để trống.")
                    if not ten_don_vi:
                        raise ValueError(f"Dòng {row_index}: TEN_DON_VI không được để trống.")
                    if ket_qua not in {"YES", "NO"}:
                        raise ValueError(f"Dòng {row_index}: KET_QUA phải là YES hoặc NO.")
                    if not can_cu:
                        raise ValueError(f"Dòng {row_index}: CAN_CU không được để trống.")

                    ma_col = target_map.get("MA_QUY_TAC")
                    ma_quy_tac = str(row.get(ma_col) or "").strip() if ma_col else ""
                    if not ma_quy_tac:
                        ma_quy_tac = f"BR_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{row_index}"

                    existing = cur.execute(
                        "SELECT id FROM business_rule WHERE ma_quy_tac=?",
                        (ma_quy_tac,),
                    ).fetchone()
                    if mode == "APPEND" and existing:
                        skipped += 1
                        continue
                    if existing:
                        cur.execute("DELETE FROM business_rule WHERE ma_quy_tac=?", (ma_quy_tac,))

                    # Business Rule chỉ được gắn với đơn vị đã tồn tại.
                    # Không tự tạo đơn vị ở đây để tránh một lỗi chính tả trong file rule
                    # vô tình sinh ra đơn vị mới. Mã đơn vị vẫn là khóa nội bộ.
                    unit = cur.execute(
                        "SELECT ma_don_vi, ten_don_vi FROM don_vi WHERE ten_don_vi_chuan=?",
                        (chuan_hoa_tim_kiem(ten_don_vi),),
                    ).fetchone()
                    if unit is None:
                        raise ValueError(
                            f"Dòng {row_index}: đơn vị '{ten_don_vi}' chưa tồn tại. "
                            "Hãy nhập đơn vị trước khi nạp Business Rule."
                        )
                    ma_don_vi = unit["ma_don_vi"]
                    ten_don_vi = unit["ten_don_vi"]
                    cur.execute(
                        """
                        INSERT INTO business_rule(
                            ma_quy_tac, ten_quy_tac, pham_vi, ma_don_vi,
                            ten_don_vi, loai_don_vi, ket_qua, can_cu,
                            muc_uu_tien, ngay_hieu_luc, ngay_het_hieu_luc,
                            dang_ap_dung, la_mock
                        ) VALUES(?,?,'DON_VI',?,?,NULL,?,?,0,NULL,NULL,1,?)
                        """,
                        (
                            ma_quy_tac,
                            ten_quy_tac,
                            ma_don_vi,
                            ten_don_vi,
                            ket_qua,
                            can_cu,
                            CommitService._mock_flag(can_cu),
                        ),
                    )
                    imported += 1

            conn.commit()
            return {
                "ok": True,
                "batch_id": f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "data_type": data_type,
                "mode": mode,
                "so_dong_import": imported,
                "so_dong_trung": skipped,
                "so_dong_loi": 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "business_decision_written": data_type in {"BUSINESS_RULE", "NHAN_VIEN_CO_KET_QUA"},
            }
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(
                f"Lỗi commit cơ sở dữ liệu (đã rollback toàn bộ transaction): {exc}"
            ) from exc
