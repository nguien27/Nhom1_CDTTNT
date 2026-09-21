import difflib
import json
import re

from src.normalization import normalize_vietnamese
from src.ranking import RankingEngine


try:
    from rapidfuzz import fuzz, distance
except ImportError:
    fuzz = None
    distance = None


class SearchEngine:
    """
    Search Engine GĐ2-03.

    Thứ tự:
    EXACT -> TOKEN -> PARTIAL -> FUZZY
    """

    FUZZY_THRESHOLD = 0.78

    def __init__(self, repo):
        self.repo = repo

    # =========================================================
    # NHÂN VIÊN
    # =========================================================

    def search_nhan_vien(
        self,
        keyword,
        page=1,
        limit=20,
        offset=None,
    ):
        query = normalize_vietnamese(keyword)

        offset = self._lay_offset(
            page,
            limit,
            offset,
        )

        if not query:
            return self._tao_response(
                keyword,
                [],
                limit,
                offset,
            )

        # Nếu giống mã nhân viên thì chỉ exact.
        if self._la_ma_nhan_vien(keyword):
            rows = self.repo.execute_query(
                """
                SELECT
                    nv.*,
                    dv.ten_don_vi AS ten_don_vi_thuc
                FROM nhan_vien nv
                LEFT JOIN don_vi dv
                    ON dv.ma_don_vi = nv.ma_don_vi
                WHERE UPPER(nv.ma_nhan_vien) = ?
                """,
                (
                    str(keyword)
                    .strip()
                    .upper(),
                ),
            )

            ket_qua = []

            for row in rows:
                ket_qua.append(
                    self._tao_ket_qua_nhan_vien(
                        row=row,
                        do_khop=1.0,
                        loai_khop="EXACT",
                        truong_khop="ma_nhan_vien",
                    )
                )

            return self._tao_response(
                keyword,
                ket_qua,
                limit,
                offset,
            )

        # EXACT / TOKEN / PARTIAL
        rows = self._candidate_chinh_nhan_vien(
            query
        )

        ket_qua = self._xep_hang_rows(
            query=query,
            rows=rows,
            loai_doi_tuong="NHAN_VIEN",
        )

        # Chỉ fuzzy nếu không có match chính xác hơn.
        if not ket_qua:
            rows_fuzzy = self._candidate_fuzzy_nhan_vien(
                query
            )

            ket_qua = self._xep_hang_rows(
                query=query,
                rows=rows_fuzzy,
                loai_doi_tuong="NHAN_VIEN",
                chi_fuzzy=True,
            )

        ket_qua = self._da_dang_hoa_theo_tang(
            ket_qua
        )

        return self._tao_response(
            keyword,
            ket_qua,
            limit,
            offset,
        )

    # =========================================================
    # ĐƠN VỊ
    # =========================================================

    def search_don_vi(
        self,
        keyword,
        page=1,
        limit=20,
        offset=None,
    ):
        query = normalize_vietnamese(keyword)

        offset = self._lay_offset(
            page,
            limit,
            offset,
        )

        if not query:
            return self._tao_response(
                keyword,
                [],
                limit,
                offset,
            )

        rows = self._candidate_chinh_don_vi(
            query
        )

        ket_qua = self._xep_hang_rows(
            query=query,
            rows=rows,
            loai_doi_tuong="DON_VI",
        )

        if not ket_qua:
            # Số đơn vị nhỏ nên có thể fuzzy toàn bộ.
            rows = self.repo.execute_query(
                "SELECT * FROM don_vi"
            )

            ket_qua = self._xep_hang_rows(
                query=query,
                rows=rows,
                loai_doi_tuong="DON_VI",
                chi_fuzzy=True,
            )

        return self._tao_response(
            keyword,
            ket_qua,
            limit,
            offset,
        )

    # =========================================================
    # CANDIDATE
    # =========================================================

    def _candidate_chinh_nhan_vien(
        self,
        query,
    ):
        tokens = query.split()

        dieu_kien = [
            "nv.ho_ten_chuan = ?",
            "nv.ho_ten_chuan LIKE ?",
        ]

        tham_so = [
            query,
            f"%{query}%",
        ]

        # Hỗ trợ TOKEN nhiều từ không liền nhau:
        # nguyen an -> Nguyen Van An
        if len(tokens) >= 2:
            token_sql = []

            for token in tokens:
                token_sql.append(
                    "nv.ho_ten_chuan LIKE ?"
                )

                tham_so.append(
                    f"%{token}%"
                )

            dieu_kien.append(
                "("
                + " AND ".join(token_sql)
                + ")"
            )

        cau_lenh = """
            SELECT
                nv.*,
                dv.ten_don_vi AS ten_don_vi_thuc
            FROM nhan_vien nv
            LEFT JOIN don_vi dv
                ON dv.ma_don_vi = nv.ma_don_vi
            WHERE
        """

        cau_lenh += " OR ".join(
            f"({item})"
            for item in dieu_kien
        )

        return self.repo.execute_query(
            cau_lenh,
            tuple(tham_so),
        )

    def _candidate_chinh_don_vi(
        self,
        query,
    ):
        tokens = query.split()

        dieu_kien = [
            "ten_don_vi_chuan = ?",
            "ten_don_vi_chuan LIKE ?",
        ]

        tham_so = [
            query,
            f"%{query}%",
        ]

        if len(tokens) >= 2:
            token_sql = []

            for token in tokens:
                token_sql.append(
                    "ten_don_vi_chuan LIKE ?"
                )

                tham_so.append(
                    f"%{token}%"
                )

            dieu_kien.append(
                "("
                + " AND ".join(token_sql)
                + ")"
            )

        cau_lenh = (
            "SELECT * FROM don_vi WHERE "
            + " OR ".join(
                f"({item})"
                for item in dieu_kien
            )
        )

        return self.repo.execute_query(
            cau_lenh,
            tuple(tham_so),
        )

    def _candidate_fuzzy_nhan_vien(
        self,
        query,
    ):
        tokens = [
            token
            for token in query.split()
            if len(token) >= 2
        ]

        if not tokens:
            return []

        # Thử thu hẹp candidate trước.
        dieu_kien = []

        tham_so = []

        for token in tokens:
            dieu_kien.append(
                "nv.ho_ten_chuan LIKE ?"
            )

            tham_so.append(
                f"%{token}%"
            )

        cau_lenh = """
            SELECT
                nv.*,
                dv.ten_don_vi AS ten_don_vi_thuc
            FROM nhan_vien nv
            LEFT JOIN don_vi dv
                ON dv.ma_don_vi = nv.ma_don_vi
            WHERE
        """

        cau_lenh += " OR ".join(
            dieu_kien
        )

        rows = self.repo.execute_query(
            cau_lenh,
            tuple(tham_so),
        )

        if rows:
            return rows

        # Trường hợp mọi token đều bị typo:
        # ngyuen -> nguyen
        #
        # Chỉ full scan khi:
        # EXACT/TOKEN/PARTIAL đã thất bại
        # và candidate fuzzy cũng rỗng.
        return self.repo.execute_query(
            """
            SELECT
                nv.*,
                dv.ten_don_vi AS ten_don_vi_thuc
            FROM nhan_vien nv
            LEFT JOIN don_vi dv
                ON dv.ma_don_vi = nv.ma_don_vi
            """
        )

    # =========================================================
    # RANKING
    # =========================================================

    def _xep_hang_rows(
        self,
        query,
        rows,
        loai_doi_tuong,
        chi_fuzzy=False,
    ):
        ket_qua = []

        da_gap = set()

        for row in rows:
            if loai_doi_tuong == "NHAN_VIEN":
                khoa = (
                    "NHAN_VIEN",
                    row.get("ma_nhan_vien"),
                )

                target = (
                    row.get("ho_ten_chuan")
                    or normalize_vietnamese(
                        row.get("ho_ten", "")
                    )
                )

            else:
                khoa = (
                    "DON_VI",
                    row.get("ma_don_vi")
                    or row.get("id"),
                )

                target = (
                    row.get("ten_don_vi_chuan")
                    or normalize_vietnamese(
                        row.get(
                            "ten_don_vi",
                            "",
                        )
                    )
                )

            if khoa in da_gap:
                continue

            da_gap.add(khoa)

            chi_tiet_fuzzy = {}

            if chi_fuzzy:
                (
                    loai_khop,
                    do_khop,
                    chi_tiet_fuzzy,
                ) = self._fuzzy_match(
                    query,
                    target,
                )

            else:
                (
                    loai_khop,
                    do_khop,
                ) = RankingEngine.classify(
                    query,
                    target,
                )

            if not loai_khop:
                continue

            if loai_doi_tuong == "NHAN_VIEN":
                item = self._tao_ket_qua_nhan_vien(
                    row=row,
                    do_khop=do_khop,
                    loai_khop=loai_khop,
                    truong_khop="ho_ten",
                    chi_tiet_fuzzy=chi_tiet_fuzzy,
                )

            else:
                item = {
                    "loai_doi_tuong": "DON_VI",

                    "id_doi_tuong": (
                        row.get("ma_don_vi")
                        or row.get("id")
                    ),

                    "ma_don_vi": row.get(
                        "ma_don_vi"
                    ),

                    "ten_don_vi": row.get(
                        "ten_don_vi"
                    ),

                    "loai_don_vi": row.get(
                        "loai_don_vi"
                    ),

                    "thong_tin_mo_rong":
                        self._doc_json(
                            row.get(
                                "thong_tin_mo_rong"
                            )
                        ),

                    "do_khop": round(
                        do_khop,
                        6,
                    ),

                    "loai_khop": loai_khop,

                    "truong_khop":
                        "ten_don_vi",

                    "ten_don_vi_chuan":
                        target,
                }

                item.update(
                    chi_tiet_fuzzy
                )

            ket_qua.append(item)

        ket_qua.sort(
            key=RankingEngine.sort_key
        )

        return ket_qua

    # =========================================================
    # FUZZY
    # =========================================================

    def _fuzzy_match(
        self,
        query,
        target,
    ):
        if not query or not target:
            return "", 0.0, {}

        if fuzz is not None:
            ratio = (
                fuzz.ratio(
                    query,
                    target,
                )
                / 100
            )

            partial_ratio = (
                fuzz.partial_ratio(
                    query,
                    target,
                )
                / 100
            )

            token_ratio = (
                fuzz.token_set_ratio(
                    query,
                    target,
                )
                / 100
            )

            levenshtein = (
                distance.Levenshtein
                .normalized_similarity(
                    query,
                    target,
                )
            )

        else:
            ratio = (
                difflib.SequenceMatcher(
                    None,
                    query,
                    target,
                ).ratio()
            )

            partial_ratio = ratio
            token_ratio = ratio
            levenshtein = ratio

        do_khop = max(
            ratio,
            partial_ratio,
            token_ratio,
            levenshtein,
        )

        if do_khop < self.FUZZY_THRESHOLD:
            return "", 0.0, {}

        return (
            "FUZZY",
            do_khop,
            {
                "ratio": round(
                    ratio,
                    6,
                ),

                "partial_ratio": round(
                    partial_ratio,
                    6,
                ),

                "token_ratio": round(
                    token_ratio,
                    6,
                ),

                "levenshtein": round(
                    levenshtein,
                    6,
                ),
            },
        )

    # =========================================================
    # DIVERSITY
    # =========================================================

    def _da_dang_hoa_theo_tang(
        self,
        ket_qua,
    ):
        """
        Diversity nhưng không được phá:

        EXACT > TOKEN > PARTIAL > FUZZY
        """

        ket_qua_cuoi = []

        for loai_khop in [
            "EXACT",
            "TOKEN",
            "PARTIAL",
            "FUZZY",
        ]:
            tang = [
                item
                for item in ket_qua
                if item.get("loai_khop")
                == loai_khop
            ]

            nhom = {}

            for item in tang:
                ten = item.get(
                    "ho_ten_chuan",
                    "",
                )

                if ten not in nhom:
                    nhom[ten] = []

                nhom[ten].append(item)

            # Round-robin trong cùng tầng.
            while nhom:
                for ten in list(
                    nhom.keys()
                ):
                    item = nhom[ten].pop(0)

                    ket_qua_cuoi.append(
                        item
                    )

                    if not nhom[ten]:
                        del nhom[ten]

        return ket_qua_cuoi

    # =========================================================
    # OUTPUT
    # =========================================================

    def _tao_ket_qua_nhan_vien(
        self,
        row,
        do_khop,
        loai_khop,
        truong_khop,
        chi_tiet_fuzzy=None,
    ):
        ten_don_vi = (
            row.get("ten_don_vi_thuc")
            or row.get("ten_don_vi")
        )

        item = {
            "loai_doi_tuong":
                "NHAN_VIEN",

            # Business identifier
            "id_doi_tuong":
                row.get(
                    "ma_nhan_vien"
                ),

            "ma_nhan_vien":
                row.get(
                    "ma_nhan_vien"
                ),

            "ho_ten":
                row.get(
                    "ho_ten"
                ),

            "ma_don_vi":
                row.get(
                    "ma_don_vi"
                ),

            "ten_don_vi":
                ten_don_vi,

            "don_vi":
                ten_don_vi,

            "thong_tin_mo_rong":
                self._doc_json(
                    row.get(
                        "thong_tin_mo_rong"
                    )
                ),

            "do_khop":
                round(
                    do_khop,
                    6,
                ),

            "loai_khop":
                loai_khop,

            "truong_khop":
                truong_khop,

            "ho_ten_chuan":
                row.get(
                    "ho_ten_chuan",
                    "",
                ),
        }

        if chi_tiet_fuzzy:
            item.update(
                chi_tiet_fuzzy
            )

        return item

    def _tao_response(
        self,
        query,
        ket_qua,
        limit,
        offset,
    ):
        tong = len(ket_qua)

        trang_hien_tai = (
            ket_qua[
                offset:
                offset + limit
            ]
        )

        page = (
            offset // limit
        ) + 1

        tong_trang = (
            tong + limit - 1
        ) // limit

        return {
            "query": query,

            "tong_ket_qua":
                tong,

            "limit":
                limit,

            "offset":
                offset,

            "ket_qua":
                trang_hien_tai,

            # Alias tạm tương thích code cũ
            "data":
                trang_hien_tai,

            "pagination": {
                "total":
                    tong,

                "page":
                    page,

                "limit":
                    limit,

                "offset":
                    offset,

                "total_pages":
                    tong_trang,
            },
        }

    # =========================================================
    # HELPER
    # =========================================================

    @staticmethod
    def _la_ma_nhan_vien(
        value,
    ):
        if value is None:
            return False

        value = str(value).strip()

        return bool(
            re.fullmatch(
                r"[A-Za-z]{2,}\d+",
                value,
            )
        )

    @staticmethod
    def _lay_offset(
        page,
        limit,
        offset,
    ):
        if limit <= 0:
            raise ValueError(
                "limit phải lớn hơn 0"
            )

        if offset is not None:
            if offset < 0:
                raise ValueError(
                    "offset không được âm"
                )

            return offset

        if page <= 0:
            raise ValueError(
                "page phải lớn hơn 0"
            )

        return (
            page - 1
        ) * limit

    @staticmethod
    def _doc_json(value):
        if isinstance(
            value,
            dict,
        ):
            return value

        if not value:
            return {}

        try:
            du_lieu = json.loads(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return {}

        if isinstance(
            du_lieu,
            dict,
        ):
            return du_lieu

        return {}