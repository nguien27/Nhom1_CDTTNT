from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .contracts import error_contract, finalize_contract, success_contract
from .gd2_adapter import adapt_gd2_contract, load_gd2_reader
from .text_parser import normalize_text, parse_text_tables
from .txt_reader import decode_text_bytes, read_txt


SUPPORTED_FILE_TYPES = {".csv", ".xlsx", ".docx", ".pdf", ".txt"}


class UniversalInputReader:
    """Một cổng vào an toàn cho file, bytes và chuỗi nhập trực tiếp."""

    def __init__(self, max_file_size: int = 50 * 1024 * 1024):
        self.max_file_size = max_file_size
        self._gd2_readers: dict[str, Any] = {}

    def _get_gd2_reader(self, suffix: str):
        """Lazy-load và tái sử dụng reader; đặc biệt tránh khởi tạo lại model OCR."""
        if suffix not in self._gd2_readers:
            self._gd2_readers[suffix] = load_gd2_reader(suffix)
        return self._gd2_readers[suffix]

    def read_file(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        source_type = path.suffix.lower().lstrip(".") or "file"
        try:
            if not path.exists():
                return finalize_contract(error_contract(source_type, "FILE_NOT_FOUND", "Không tìm thấy file.", filename=path.name))
            if not path.is_file():
                return finalize_contract(error_contract(source_type, "NOT_A_FILE", "Đường dẫn không phải là file.", filename=path.name))
            size = path.stat().st_size
            if size == 0:
                return finalize_contract(error_contract(source_type, "EMPTY_FILE", "File rỗng.", filename=path.name, file_size=0))
            if size > self.max_file_size:
                return finalize_contract(error_contract(source_type, "FILE_TOO_LARGE", "File vượt quá giới hạn kích thước.", filename=path.name, file_size=size))
            if path.suffix.lower() not in SUPPORTED_FILE_TYPES:
                return finalize_contract(error_contract(source_type, "UNSUPPORTED_FILE_TYPE", f"Không hỗ trợ định dạng {path.suffix}.", filename=path.name, file_size=size))
            if path.suffix.lower() == ".txt":
                text, encoding, warnings = read_txt(path)
                return self._text_contract(text, "txt", filename=path.name, encoding=encoding, warnings=warnings, file_size=size)
            return adapt_gd2_contract(self._get_gd2_reader(path.suffix.lower()).read(path), path.name)
        except (UnicodeError, ValueError) as exc:
            return finalize_contract(error_contract(source_type, "ENCODING_ERROR", str(exc), filename=path.name))
        except Exception as exc:  # ranh giới chống crash Backend
            return finalize_contract(error_contract(source_type, "INPUT_READ_ERROR", f"Không đọc được input: {exc}", filename=path.name))

    def read_bytes(self, content: bytes, filename: str) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        source_type = suffix.lstrip(".") or "file"
        try:
            if not content:
                return finalize_contract(error_contract(source_type, "EMPTY_FILE", "File rỗng.", filename=filename, file_size=0))
            if len(content) > self.max_file_size:
                return finalize_contract(error_contract(source_type, "FILE_TOO_LARGE", "File vượt quá giới hạn kích thước.", filename=filename, file_size=len(content)))
            if suffix not in SUPPORTED_FILE_TYPES:
                return finalize_contract(error_contract(source_type, "UNSUPPORTED_FILE_TYPE", f"Không hỗ trợ định dạng {suffix}.", filename=filename, file_size=len(content)))
            if suffix == ".txt":
                text, encoding, warnings = decode_text_bytes(content)
                return self._text_contract(text, "txt", filename=filename, encoding=encoding, warnings=warnings, file_size=len(content))
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(content)
                temporary_path = Path(handle.name)
            try:
                return adapt_gd2_contract(self._get_gd2_reader(suffix).read(temporary_path), filename)
            finally:
                temporary_path.unlink(missing_ok=True)
        except (UnicodeError, ValueError) as exc:
            return finalize_contract(error_contract(source_type, "ENCODING_ERROR", str(exc), filename=filename))
        except Exception as exc:
            return finalize_contract(error_contract(source_type, "INPUT_READ_ERROR", f"Không đọc được input: {exc}", filename=filename))

    def read_string(self, text: str) -> dict[str, Any]:
        try:
            normalized = normalize_text("" if text is None else str(text))
            if not normalized:
                return finalize_contract(error_contract("raw_string", "EMPTY_STRING", "Chuỗi đầu vào rỗng."))
            return self._text_contract(normalized, "raw_string", parser="direct_memory")
        except Exception as exc:
            return finalize_contract(error_contract("raw_string", "STRING_READ_ERROR", f"Không xử lý được chuỗi: {exc}"))

    @staticmethod
    def _text_contract(text: str, source_type: str, warnings: list[str] | None = None, **metadata: Any) -> dict[str, Any]:
        normalized = normalize_text(text)
        if not normalized:
            code = "EMPTY_STRING" if source_type == "raw_string" else "EMPTY_FILE"
            return finalize_contract(error_contract(source_type, code, "Đầu vào không chứa văn bản.", **metadata))
        result = success_contract(source_type, **metadata)
        result["text"] = normalized
        result["tables"] = parse_text_tables(normalized, "Raw_String" if source_type == "raw_string" else "TXT_1")
        result["warnings"] = list(warnings or [])
        return finalize_contract(result)


_default_reader = UniversalInputReader()


def doc_file(file_path: str | Path) -> dict[str, Any]:
    return _default_reader.read_file(file_path)


def doc_bytes(content: bytes, filename: str) -> dict[str, Any]:
    return _default_reader.read_bytes(content, filename)


def doc_chuoi(van_ban: str) -> dict[str, Any]:
    """Đọc trực tiếp trong RAM; không tạo file TXT trung gian."""
    return _default_reader.read_string(van_ban)
