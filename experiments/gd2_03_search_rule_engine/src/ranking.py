class RankingEngine:
    """
    Xác định loại khớp và thứ tự ưu tiên kết quả tìm kiếm.

    Thứ tự:
    EXACT > TOKEN > PARTIAL > FUZZY
    """

    MATCH_ORDER = {
        "EXACT": 4,
        "TOKEN": 3,
        "PARTIAL": 2,
        "FUZZY": 1,
    }

    @staticmethod
    def classify(query: str, target: str):
        """
        Phân loại mức khớp giữa query và target.

        Trả về:
        (loai_khop, do_khop)
        """

        if not query or not target:
            return "", 0.0

        # 1. Exact
        if query == target:
            return "EXACT", 1.0

        query_tokens = query.split()
        target_tokens = target.split()

        # 2. Token
        # Tất cả token trong query phải xuất hiện
        # dưới dạng token đầy đủ trong target.
        if query_tokens:
            tap_target = set(target_tokens)

            if all(token in tap_target for token in query_tokens):
                do_khop = len(query_tokens) / max(len(target_tokens), 1)
                return "TOKEN", do_khop

        # 3. Partial
        if query in target:
            do_khop = len(query) / max(len(target), 1)
            return "PARTIAL", do_khop

        return "", 0.0

    @staticmethod
    def sort_key(result: dict):
        """
        Key dùng để sort kết quả.

        Ưu tiên:
        1. Loại match
        2. Độ khớp
        3. Tên chuẩn hóa
        4. Mã đối tượng
        """

        loai_khop = result.get("loai_khop", "")
        do_khop = result.get("do_khop", 0.0)

        ten_chuan = (
            result.get("ho_ten_chuan")
            or result.get("ten_don_vi_chuan")
            or ""
        )

        ma_doi_tuong = (
            result.get("ma_nhan_vien")
            or result.get("ma_don_vi")
            or ""
        )

        return (
            -RankingEngine.MATCH_ORDER.get(loai_khop, 0),
            -do_khop,
            ten_chuan,
            ma_doi_tuong,
        )