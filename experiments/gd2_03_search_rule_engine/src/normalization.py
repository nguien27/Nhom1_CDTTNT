import re
import unicodedata


def chuan_hoa_tieng_viet(text: str) -> str:
    """
    Chuẩn hóa chuỗi tiếng Việt để phục vụ tìm kiếm.

    Các bước:
    - Unicode normalization
    - lowercase
    - bỏ dấu
    - đổi đ -> d
    - gộp khoảng trắng
    """

    if text is None:
        return ""

    text = str(text).strip()

    if not text:
        return ""

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        ky_tu
        for ky_tu in text
        if not unicodedata.combining(ky_tu)
    )

    text = text.replace("đ", "d").replace("Đ", "D")

    text = text.lower()

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# Alias tương thích code cũ
normalize_vietnamese = chuan_hoa_tieng_viet