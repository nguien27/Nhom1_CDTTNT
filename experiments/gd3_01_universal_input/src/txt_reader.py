from __future__ import annotations

from pathlib import Path


ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "cp1252")


def decode_text_bytes(content: bytes) -> tuple[str, str, list[str]]:
    if not content:
        raise ValueError("EMPTY_INPUT")
    for encoding in ENCODINGS:
        try:
            text = content.decode(encoding, errors="strict")
            warnings = []
            if encoding not in {"utf-8", "utf-8-sig"}:
                warnings.append(f"TXT được đọc bằng encoding fallback: {encoding}")
            return text, encoding, warnings
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Không giải mã được TXT bằng các encoding được hỗ trợ.")


def read_txt(path: str | Path) -> tuple[str, str, list[str]]:
    return decode_text_bytes(Path(path).read_bytes())

