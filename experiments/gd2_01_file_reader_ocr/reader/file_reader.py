from __future__ import annotations

from pathlib import Path

from .csv_reader import CsvReader
from .xlsx_reader import XlsxReader
from .docx_reader import DocxReader
from .pdf_reader import PdfReader


class FileReader:
    """Dieu phoi reader theo dinh dang file."""

    def __init__(self):
        self.readers = {
            ".csv": CsvReader(),
            ".xlsx": XlsxReader(),
            ".docx": DocxReader(),
            ".pdf": PdfReader(),
        }

    @staticmethod
    def _tao_loi(loi: str, file_type=None) -> dict:
        return {
            "status": "error",
            "file_type": file_type,
            "pdf_mode": None,
            "ocr_da_su_dung": False,
            "du_lieu": [],
            "canh_bao": [],
            "loi": loi,
        }

    def read(self, file_path: str | Path) -> dict:
        path = Path(file_path)

        try:
            if not path.exists():
                return self._tao_loi("FILE_NOT_FOUND")

            if not path.is_file():
                return self._tao_loi("NOT_A_FILE")

            if path.stat().st_size == 0:
                return self._tao_loi("EMPTY_FILE")

            ext = path.suffix.lower()

            if ext not in self.readers:
                return self._tao_loi("UNSUPPORTED_FILE_TYPE")

            reader = self.readers[ext]
            result = reader.read(path)

            # Dam bao output contract luon day du
            result.setdefault("status", "error")
            result.setdefault("file_type", ext[1:])
            result.setdefault("pdf_mode", None)
            result.setdefault("ocr_da_su_dung", False)
            result.setdefault("du_lieu", [])
            result.setdefault("canh_bao", [])
            result.setdefault("loi", None)

            if result["status"] == "error" and not result["loi"]:
                result["loi"] = "FILE_READ_ERROR"

            return result

        except Exception as e:
            return self._tao_loi(
                f"INTERNAL_ERROR: {str(e)}"
            )