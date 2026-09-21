"""Tiền xử lý tên cột cho AI Schema Mapping."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def chuan_hoa_unicode(text: Optional[str]) -> str:
    """Chuẩn hóa Unicode về NFC."""
    if text is None:
        return ""
    return unicodedata.normalize("NFC", str(text))


def strip_accents(text: Optional[str]) -> str:
    """Bỏ dấu tiếng Việt và chuyển đ/Đ về d/D."""
    text = chuan_hoa_unicode(text)
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def preprocess(text: Optional[str]) -> str:
    """Chuẩn hóa vừa đủ, không làm mất chữ/số có ý nghĩa."""
    text = chuan_hoa_unicode(text).lower().strip()
    # Các ký tự phân cách thường gặp trong header -> khoảng trắng.
    text = re.sub(r"[_\-\\./,;:|()\[\]{}]+", " ", text)
    # Loại ký tự đặc biệt còn lại, giữ chữ/số Unicode và khoảng trắng.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_no_accent(text: Optional[str]) -> str:
    """Preprocess rồi bỏ dấu; dùng cho alias và khóa nhóm chống leakage."""
    return strip_accents(preprocess(text)).lower().strip()
