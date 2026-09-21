from datetime import date


class RuleEngine:
    """
    Rule Engine xác định:

    YES
    NO
    CHUA_XAC_DINH
    """

    def __init__(self, repo):
        self.repo = repo

    # =========================================================
    # NHÂN VIÊN
    # =========================================================

    def evaluate_employee_salary_rule(
        self,
        ma_nhan_vien,
        ngay_kiem_tra=None,
    ):
        ngay = (
            ngay_kiem_tra
            or date.today().isoformat()
        )

        nhan_vien = self.repo.execute_query(
            """
            SELECT
                nv.ma_nhan_vien,
                nv.ma_don_vi,
                nv.ten_don_vi,
                dv.loai_don_vi
            FROM nhan_vien nv
            LEFT JOIN don_vi dv
                ON dv.ma_don_vi = nv.ma_don_vi
            WHERE UPPER(nv.ma_nhan_vien) = ?
            """,
            (
                str(ma_nhan_vien)
                .strip()
                .upper(),
            ),
        )

        if not nhan_vien:
            return self._chua_xac_dinh(
                "Không tìm thấy nhân viên."
            )

        # -----------------------------------------
        # 1. Ngoại lệ cá nhân
        # -----------------------------------------

        ngoai_le = self.repo.execute_query(
            """
            SELECT *
            FROM ngoai_le_ca_nhan
            WHERE UPPER(ma_nhan_vien) = ?
              AND dang_ap_dung = 1
            """,
            (
                str(ma_nhan_vien)
                .strip()
                .upper(),
            ),
        )

        ngoai_le_hop_le = [
            item
            for item in ngoai_le
            if self._con_hieu_luc(
                item,
                ngay,
            )
        ]

        if ngoai_le_hop_le:
            rule = max(
                ngoai_le_hop_le,
                key=self._khoa_ngoai_le,
            )

            return self._tao_ket_qua(
                ket_qua=rule.get(
                    "ket_qua"
                ),

                can_cu=rule.get(
                    "can_cu"
                ),

                ma_quy_tac=rule.get(
                    "ma_quy_tac"
                ),

                nguon_quy_tac=
                    "ngoai_le_ca_nhan",

                rule=rule,

                pham_vi=
                    "NGOAI_LE_CA_NHAN",

                ngay_kiem_tra=ngay,
            )

        row = nhan_vien[0]

        return self._danh_gia_don_vi(
            ma_don_vi=row.get(
                "ma_don_vi"
            ),

            loai_don_vi=row.get(
                "loai_don_vi"
            ),

            ngay_kiem_tra=ngay,
        )

    # =========================================================
    # ĐƠN VỊ
    # =========================================================

    def evaluate_unit_salary_rule(
        self,
        ma_don_vi,
        ngay_kiem_tra=None,
    ):
        ngay = (
            ngay_kiem_tra
            or date.today().isoformat()
        )

        don_vi = self.repo.execute_query(
            """
            SELECT
                ma_don_vi,
                loai_don_vi
            FROM don_vi
            WHERE UPPER(ma_don_vi) = ?
            """,
            (
                str(ma_don_vi)
                .strip()
                .upper(),
            ),
        )

        if not don_vi:
            return self._chua_xac_dinh(
                "Không tìm thấy đơn vị."
            )

        row = don_vi[0]

        return self._danh_gia_don_vi(
            ma_don_vi=row.get(
                "ma_don_vi"
            ),

            loai_don_vi=row.get(
                "loai_don_vi"
            ),

            ngay_kiem_tra=ngay,
        )

    # =========================================================
    # BUSINESS RULE
    # =========================================================

    def _danh_gia_don_vi(
        self,
        ma_don_vi,
        loai_don_vi,
        ngay_kiem_tra,
    ):
        if (
            not ma_don_vi
            and not loai_don_vi
        ):
            return self._chua_xac_dinh(
                "Đối tượng chưa có thông tin đơn vị."
            )

        rules = self.repo.execute_query(
            """
            SELECT *
            FROM quy_tac_tra_luong
            WHERE dang_ap_dung = 1
              AND (
                    (
                        pham_vi = 'DON_VI'
                        AND UPPER(ma_don_vi)
                            = UPPER(?)
                    )
                    OR
                    (
                        pham_vi = 'LOAI_DON_VI'
                        AND loai_don_vi = ?
                    )
              )
            """,
            (
                ma_don_vi,
                loai_don_vi,
            ),
        )

        rules = [
            rule
            for rule in rules
            if self._con_hieu_luc(
                rule,
                ngay_kiem_tra,
            )
        ]

        if not rules:
            return self._chua_xac_dinh(
                "Chưa có quy tắc đang hiệu lực áp dụng."
            )

        rule = max(
            rules,
            key=self._khoa_rule,
        )

        return self._tao_ket_qua(
            ket_qua=rule.get(
                "ket_qua"
            ),

            can_cu=rule.get(
                "can_cu"
            ),

            ma_quy_tac=rule.get(
                "ma_quy_tac"
            ),

            nguon_quy_tac=
                self._xac_dinh_nguon(
                    rule
                ),

            rule=rule,

            pham_vi=rule.get(
                "pham_vi"
            ),

            ngay_kiem_tra=
                ngay_kiem_tra,
        )

    # =========================================================
    # PRIORITY
    # =========================================================

    @staticmethod
    def _khoa_rule(rule):
        """
        Ưu tiên:
        1. DON_VI
        2. LOAI_DON_VI
        3. muc_uu_tien
        4. ngay_hieu_luc mới hơn
        5. ma_quy_tac ổn định
        """

        uu_tien_pham_vi = (
            1
            if rule.get("pham_vi")
            == "DON_VI"
            else 0
        )

        return (
            uu_tien_pham_vi,

            int(
                rule.get(
                    "muc_uu_tien"
                )
                or 0
            ),

            rule.get(
                "ngay_hieu_luc"
            )
            or "",

            rule.get(
                "ma_quy_tac"
            )
            or "",
        )

    @staticmethod
    def _khoa_ngoai_le(rule):
        """
        Nếu có nhiều ngoại lệ đang hiệu lực:

        muc_uu_tien
        -> ngày hiệu lực mới hơn
        -> ma_quy_tac
        """

        return (
            int(
                rule.get(
                    "muc_uu_tien"
                )
                or 0
            ),

            rule.get(
                "ngay_hieu_luc"
            )
            or "",

            rule.get(
                "ma_quy_tac"
            )
            or "",

            rule.get("id")
            or 0,
        )

    # =========================================================
    # TIME
    # =========================================================

    @staticmethod
    def _con_hieu_luc(
        rule,
        ngay_kiem_tra,
    ):
        ngay_bat_dau = rule.get(
            "ngay_hieu_luc"
        )

        ngay_ket_thuc = rule.get(
            "ngay_het_hieu_luc"
        )

        if (
            ngay_bat_dau
            and ngay_bat_dau
            > ngay_kiem_tra
        ):
            return False

        if (
            ngay_ket_thuc
            and ngay_ket_thuc
            < ngay_kiem_tra
        ):
            return False

        return True

    # =========================================================
    # OUTPUT
    # =========================================================

    @staticmethod
    def _xac_dinh_nguon(rule):
        can_cu = (
            rule.get(
                "can_cu"
            )
            or ""
        ).strip().lower()

        if (
            can_cu.startswith(
                "mock"
            )
            or can_cu.startswith(
                "[mock]"
            )
        ):
            return "MOCK"

        return "quy_tac_tra_luong"

    @classmethod
    def _tao_ket_qua(
        cls,
        ket_qua,
        can_cu,
        ma_quy_tac,
        nguon_quy_tac,
        rule,
        pham_vi,
        ngay_kiem_tra,
    ):
        can_cu = (
            can_cu
            or ""
        ).strip()

        if ket_qua not in [
            "YES",
            "NO",
        ]:
            return cls._chua_xac_dinh(
                "Quy tắc có kết quả không hợp lệ."
            )

        # YES / NO bắt buộc có căn cứ.
        if not can_cu:
            return cls._chua_xac_dinh(
                f"Quy tắc {ma_quy_tac or '(không mã)'} thiếu căn cứ."
            )

        if (
            cls._xac_dinh_nguon(
                rule
            )
            == "MOCK"
        ):
            nguon_quy_tac = "MOCK"

            if not can_cu.lower().startswith(
                "[mock]"
            ):
                can_cu = (
                    "[MOCK] "
                    + can_cu
                )

        return {
            "ket_qua":
                ket_qua,

            "ma_quy_tac":
                ma_quy_tac,

            "can_cu":
                can_cu,

            "nguon_quy_tac":
                nguon_quy_tac,

            "muc_uu_tien":
                rule.get(
                    "muc_uu_tien"
                ),

            "ngay_hieu_luc":
                rule.get(
                    "ngay_hieu_luc"
                ),

            "ngay_het_hieu_luc":
                rule.get(
                    "ngay_het_hieu_luc"
                ),

            "ghi_chu":
                rule.get(
                    "ghi_chu"
                ),

            "pham_vi":
                pham_vi,

            "ngay_kiem_tra":
                ngay_kiem_tra,

            # Alias giữ tương thích code cũ
            "status":
                "success",

            "result":
                ket_qua,

            "applied_rule":
                ma_quy_tac,

            "evidence":
                can_cu,
        }

    @staticmethod
    def _chua_xac_dinh(
        can_cu,
    ):
        return {
            "ket_qua":
                "CHUA_XAC_DINH",

            "ma_quy_tac":
                None,

            "can_cu":
                can_cu,

            "nguon_quy_tac":
                None,

            "ghi_chu":
                None,

            "status":
                "success",

            "result":
                "CHUA_XAC_DINH",
        }