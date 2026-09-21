from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

from .contracts import error_contract, finalize_contract, success_contract, table_to_text


PAGE_PATTERN = re.compile(r"^Page_(\d+)(?:_(.*))?$")


GD2_01_FOLDER_NAMES = ("gd2_01_reader_ocr", "gd2_01_file_reader_ocr")


def _is_gd2_01_root(path: Path) -> bool:
    return (path / "reader" / "file_reader.py").is_file()


def find_gd2_01(start: Path | None = None) -> Path:
    """Tìm GĐ2-01 mới nhất; không bao giờ fallback về module GĐ1.

    Tên canonical theo task/repo Leader là ``gd2_01_reader_ocr``.
    ``gd2_01_file_reader_ocr`` được giữ như alias tương thích với gói GĐ2-01 cũ.
    """
    here = (start or Path(__file__)).resolve()
    parents = [here.parent, *here.parents]

    # Ưu tiên cấu trúc experiments/<module> của repo chính.
    for parent in parents:
        bases = [parent]
        if parent.name != "experiments":
            bases.append(parent / "experiments")
        for base in bases:
            for folder_name in GD2_01_FOLDER_NAMES:
                candidate = base / folder_name
                if _is_gd2_01_root(candidate):
                    return candidate

    expected = " hoặc ".join(f"experiments/{name}" for name in GD2_01_FOLDER_NAMES)
    raise FileNotFoundError(f"Không tìm thấy GĐ2-01 ({expected}).")


def load_gd2_file_reader():
    root = find_gd2_01()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("reader.file_reader").FileReader


def load_gd2_reader(extension: str):
    """Khởi tạo đúng reader GĐ2 theo định dạng, tránh nạp OCR cho CSV/XLSX/DOCX."""
    root = find_gd2_01()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    readers = {
        ".csv": ("reader.csv_reader", "CsvReader"),
        ".xlsx": ("reader.xlsx_reader", "XlsxReader"),
        ".docx": ("reader.docx_reader", "DocxReader"),
    }
    if extension.lower() == ".pdf":
        pdf_class = importlib.import_module("reader.pdf_reader").PdfReader
        ocr_class = importlib.import_module("reader.ocr_engine").OcrEngine

        class AdvancedOcrEngine(ocr_class):
            """Giữ pipeline GĐ2, chọn model mobile phù hợp CPU cho PaddleOCR.

            Hỗ trợ cả tên hàm khởi tạo của các bản GĐ2-01 cũ/mới
            (``_khoi_tao`` và ``_init_ocr``).
            """

            def _init_mobile_ocr(self):
                try:
                    from paddleocr import PaddleOCR

                    try:
                        # PaddleOCR 3.x
                        self.ocr_instance = PaddleOCR(
                            text_detection_model_name="PP-OCRv5_mobile_det",
                            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
                            device="cpu",
                            enable_mkldnn=False,
                            use_doc_orientation_classify=False,
                            use_doc_unwarping=False,
                            use_textline_orientation=False,
                        )
                    except TypeError:
                        # API cũ hơn: để engine GĐ2 tự khởi tạo theo cách tương thích.
                        base_init = getattr(super(), "_init_ocr", None) or getattr(super(), "_khoi_tao", None)
                        if base_init is None:
                            raise
                        base_init()
                except Exception as exc:
                    self.ocr_instance = None
                    self.init_error = str(exc)

            def _init_ocr(self):
                self._init_mobile_ocr()

            def _khoi_tao(self):
                self._init_mobile_ocr()

        class LazyOcrPdfReader(pdf_class):
            """Giữ thuật toán PDF GĐ2, chỉ nạp model khi thực sự gặp trang scan.

            Hỗ trợ cả tên method scan ``_process_scan_page`` và ``_xu_ly_scan``
            giữa các phiên bản GĐ2-01.
            """

            def __init__(self):
                self.ocr_engine = None

            def _ensure_ocr(self):
                if self.ocr_engine is None:
                    self.ocr_engine = AdvancedOcrEngine()

            def _process_scan_page(self, page, page_num, result):
                self._ensure_ocr()
                base_method = getattr(super(), "_process_scan_page", None)
                if base_method is not None:
                    return base_method(page, page_num, result)
                return super()._xu_ly_scan(page, page_num, result)

            def _xu_ly_scan(self, page, page_num, result):
                self._ensure_ocr()
                base_method = getattr(super(), "_xu_ly_scan", None)
                if base_method is not None:
                    return base_method(page, page_num, result)
                return super()._process_scan_page(page, page_num, result)

        return LazyOcrPdfReader()
    try:
        module_name, class_name = readers[extension.lower()]
    except KeyError as exc:
        raise ValueError(f"GĐ2-01 không hỗ trợ extension: {extension}") from exc
    return getattr(importlib.import_module(module_name), class_name)()


def _convert_table(block: dict[str, Any], index: int) -> dict[str, Any]:
    headers = [str(item) for item in (block.get("headers") or [])]
    sheet_name = block.get("sheet_name")
    if sheet_name:
        name = str(sheet_name)
    elif headers == ["noi_dung"]:
        # Reader DOCX/PDF GĐ2 dùng sheet_name=None cho paragraph. Đặt tên riêng
        # để không đụng với Table_1 của bảng thật trong cùng tài liệu.
        name = f"Paragraphs_{index}"
    else:
        name = f"Table_{index}"
    return {
        "name": name,
        "headers": headers,
        "rows": [dict(row) for row in (block.get("rows") or []) if isinstance(row, dict)],
        "kind": "reader_block",
    }


def _normalize_error_code(source_type: str, detail: str) -> str:
    known_codes = {
        "FILE_NOT_FOUND",
        "EMPTY_FILE",
        "UNSUPPORTED_FILE_TYPE",
        "FILE_TOO_LARGE",
        "OCR_UNAVAILABLE_OR_FAILED",
        "INTERNAL_ERROR",
    }
    prefix = detail.split(":", 1)[0].strip()
    if prefix in known_codes:
        return prefix
    return {
        "csv": "CSV_READ_ERROR",
        "xlsx": "XLSX_READ_ERROR",
        "docx": "DOCX_READ_ERROR",
        "pdf": "PDF_READ_ERROR",
    }.get(source_type, "FILE_READ_ERROR")


def adapt_gd2_contract(raw: dict[str, Any], filename: str | None = None) -> dict[str, Any]:
    source_type = str(raw.get("file_type") or Path(filename or "").suffix.lstrip(".") or "file").lower()
    warnings = [str(value) for value in (raw.get("canh_bao") or [])]
    metadata = {
        "filename": filename,
        "pdf_mode": raw.get("pdf_mode"),
        "ocr_used": bool(raw.get("ocr_da_su_dung")),
        "source_module": "GD2-01",
    }
    if raw.get("status") != "success":
        detail = str(raw.get("loi") or "FILE_READ_ERROR")
        code = _normalize_error_code(source_type, detail)
        return finalize_contract(error_contract(source_type, code, detail, warnings=warnings, **metadata))

    # Với PDF scan thuần, nếu GĐ2 không OCR được và cũng không tạo ra dữ liệu,
    # trả lỗi rõ ràng thay vì báo success rỗng. PDF mixed vẫn có thể trả phần text
    # cùng warning nếu một trang scan gặp lỗi.
    if (
        source_type == "pdf"
        and str(raw.get("pdf_mode") or "").lower() == "scan"
        and not bool(raw.get("ocr_da_su_dung"))
        and not (raw.get("du_lieu") or [])
    ):
        detail = str(raw.get("loi") or "OCR_UNAVAILABLE_OR_FAILED")
        return finalize_contract(
            error_contract(
                source_type,
                "OCR_UNAVAILABLE_OR_FAILED",
                detail,
                warnings=warnings or ["PDF scan không thể OCR."],
                **metadata,
            )
        )

    result = success_contract(source_type, **metadata)
    result["warnings"] = warnings
    page_map: dict[int, dict[str, Any]] = {}
    text_parts: list[str] = []
    for index, block in enumerate(raw.get("du_lieu") or [], 1):
        table = _convert_table(block, index)
        result["tables"].append(table)
        block_text = table_to_text(table)
        if block_text:
            text_parts.append(block_text)
        match = PAGE_PATTERN.match(str(table["name"]))
        if match:
            number = int(match.group(1))
            page = page_map.setdefault(number, {"page_number": number, "mode": None, "text": "", "tables": []})
            suffix = (match.group(2) or "").lower()
            if "ocr" in suffix:
                page["mode"] = "scan"
            elif page["mode"] is None:
                page["mode"] = "text"
            page["tables"].append(table)
            if block_text:
                page["text"] = "\n".join(filter(None, [page["text"], block_text]))
    result["pages"] = [page_map[key] for key in sorted(page_map)]
    result["text"] = "\n\n".join(text_parts)
    return finalize_contract(result)
