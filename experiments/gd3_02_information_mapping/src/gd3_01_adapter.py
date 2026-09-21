"""Adapter GĐ3-01 Universal Input.

GĐ3-02 không đọc lại CSV/XLSX/DOCX/PDF/OCR/TXT. File và Raw String được
chuyển qua public API của ``experiments/gd3_01_universal_input``.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict


class GD301AdapterError(RuntimeError):
    pass


def _find_project_root() -> Path:
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if (candidate / "experiments" / "gd3_01_universal_input" / "src" / "universal_input.py").is_file():
            return candidate

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "experiments" / "gd3_01_universal_input" / "src" / "universal_input.py"
        if candidate.is_file():
            return parent

    raise GD301AdapterError(
        "Không tìm thấy experiments/gd3_01_universal_input. "
        "Hãy đặt GĐ3-02 cùng repo với GĐ3-01 hoặc cấu hình PROJECT_ROOT."
    )


def _load_public_api():
    project_root = _find_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        return importlib.import_module("experiments.gd3_01_universal_input.src")
    except Exception as exc:
        raise GD301AdapterError(f"Không import được public API GĐ3-01: {exc}") from exc


def normalize_contract(result: Any) -> Dict[str, Any]:
    """Kiểm tra và làm đầy đủ contract mà không tự parse lại dữ liệu."""
    if not isinstance(result, dict):
        raise GD301AdapterError("GĐ3-01 phải trả về dict contract.")

    normalized = {
        "status": result.get("status", "error"),
        "source_type": result.get("source_type", "unknown"),
        "text": str(result.get("text") or ""),
        "tables": list(result.get("tables") or []),
        "pages": list(result.get("pages") or []),
        "metadata": dict(result.get("metadata") or {}),
        "warnings": list(result.get("warnings") or []),
        "error": result.get("error"),
    }
    normalized["success"] = normalized["status"] == "success" and normalized["error"] is None
    normalized["metadata"].setdefault("source_module", "GD3-01")
    return normalized


def read_file(file_path: str | Path) -> Dict[str, Any]:
    path = Path(file_path)
    api = _load_public_api()
    function = getattr(api, "doc_file", None)
    if not callable(function):
        raise GD301AdapterError("GĐ3-01 không export doc_file().")
    return normalize_contract(function(path))


def read_raw_text(raw_text: str) -> Dict[str, Any]:
    api = _load_public_api()
    function = getattr(api, "doc_chuoi", None)
    if not callable(function):
        raise GD301AdapterError("GĐ3-01 không export doc_chuoi().")
    return normalize_contract(function(raw_text))
