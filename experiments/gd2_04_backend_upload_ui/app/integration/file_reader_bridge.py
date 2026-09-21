from __future__ import annotations
import importlib
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _find_gd2_01() -> Path:
    here = Path(__file__).resolve()
    experiments = here.parents[3]
    candidates = [
        experiments / "gd2_01_file_reader_ocr",
        experiments / "gd1_02_reader_ocr" / "experiments" / "gd1_02_file_reader_ocr",
    ]
    for p in candidates:
        if (p / "reader" / "file_reader.py").exists():
            return p
    raise RuntimeError("Không tìm thấy GĐ2-01 File Reader/OCR cạnh GĐ2-04.")


def _load_file_reader_class():
    root = _find_gd2_01()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    module = importlib.import_module("reader.file_reader")
    return module.FileReader


def read_file(content: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
    if not content:
        raise ValueError("EMPTY_FILE")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".docx", ".pdf"}:
        raise ValueError(f"UNSUPPORTED_FILE_TYPE: {suffix}")

    FileReader = _load_file_reader_class()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)
    try:
        result = FileReader().read(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)

    if result.get("status") != "success":
        error = result.get("loi") or "FILE_READ_ERROR"
        warnings = result.get("canh_bao") or []
        detail = f"{error}; warnings={warnings}" if warnings else str(error)
        raise ValueError(detail)

    blocks = result.get("du_lieu") or []
    if not blocks:
        return [], [], {
            "loai_file": result.get("file_type"),
            "pdf_mode": result.get("pdf_mode"),
            "ocr_da_su_dung": bool(result.get("ocr_da_su_dung")),
            "canh_bao": result.get("canh_bao") or [],
            "source_module": "GD2-01",
        }

    headers: List[str] = []
    rows: List[Dict[str, Any]] = []
    for block in blocks:
        block_headers = [str(h).strip() for h in (block.get("headers") or []) if str(h).strip()]
        for h in block_headers:
            if h not in headers:
                headers.append(h)
        for row in block.get("rows") or []:
            if isinstance(row, dict):
                rows.append({str(k).strip(): v for k, v in row.items()})

    metadata = {
        "loai_file": result.get("file_type"),
        "pdf_mode": result.get("pdf_mode"),
        "ocr_da_su_dung": bool(result.get("ocr_da_su_dung")),
        "canh_bao": result.get("canh_bao") or [],
        "so_dong": len(rows),
        "source_module": "GD2-01",
    }
    return headers, rows, metadata
