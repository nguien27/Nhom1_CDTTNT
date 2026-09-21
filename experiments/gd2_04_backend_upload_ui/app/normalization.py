from __future__ import annotations
import re
import unicodedata
from typing import Optional


def chuan_hoa_unicode(text: Optional[str]) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    return re.sub(r"\s+", " ", text).strip()


def chuan_hoa_ho_ten(text: Optional[str]) -> str:
    return chuan_hoa_unicode(text)


def chuan_hoa_tim_kiem(text: Optional[str]) -> str:
    text = chuan_hoa_unicode(text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def chuan_hoa_ho_ten_chuan(text: Optional[str]) -> str:
    return chuan_hoa_tim_kiem(text)


def chuan_hoa_ten_don_vi(text: Optional[str]) -> str:
    return chuan_hoa_unicode(text)


def chuan_hoa_msnv(text: Optional[str]) -> str:
    return chuan_hoa_unicode(text).upper()


def chuan_hoa_ket_qua(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    value = chuan_hoa_tim_kiem(text).replace("_", " ")
    yes = {"yes", "y", "co", "duoc", "dong y", "true", "1"}
    no = {"no", "n", "khong", "tu choi", "false", "0"}
    if value in yes:
        return "YES"
    if value in no:
        return "NO"
    return None
