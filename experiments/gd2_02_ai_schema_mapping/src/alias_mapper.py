"""Alias Exact Match - chỉ đọc alias từ config/field_aliases.json ở root repo."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .preprocessing import preprocess, preprocess_no_accent

ALLOWED_LABELS = {
    "MA_NHAN_VIEN",
    "HO_TEN",
    "TEN_DON_VI",
    "LOAI_DON_VI",
    "OTHER",
}


def tim_root_alias() -> Path:
    """Tìm source-of-truth alias từ root repo, không dùng bản sao trong experiment."""
    env_path = os.getenv("SCHEMA_MAPPING_ALIAS_PATH")
    if env_path:
        return Path(env_path).resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "config" / "field_aliases.json"
        if candidate.exists() and "gd2_02_ai_schema_mapping" not in str(candidate.parent):
            return candidate
    # Đường dẫn dự kiến khi module nằm đúng experiments/gd2_02...
    return Path(__file__).resolve().parents[3] / "config" / "field_aliases.json"


DEFAULT_ALIAS_PATH = str(tim_root_alias())


class AliasMapper:
    def __init__(self, alias_path: str | os.PathLike | None = None):
        self.alias_path = Path(alias_path or DEFAULT_ALIAS_PATH).resolve()
        self.alias_map: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.alias_path.exists():
            raise FileNotFoundError(f"Không tìm thấy root alias: {self.alias_path}")

        raw = json.loads(self.alias_path.read_text(encoding="utf-8"))
        for label, aliases in raw.items():
            # Kiến trúc GĐ2-02 chỉ cho phép 5 class; bỏ qua class cũ nếu root còn sót.
            if label not in ALLOWED_LABELS or label == "OTHER":
                continue
            for alias in aliases:
                for key in (preprocess(alias), preprocess_no_accent(alias)):
                    if key:
                        old = self.alias_map.get(key)
                        if old is not None and old != label:
                            raise ValueError(f"Alias xung đột: {alias!r} -> {old}/{label}")
                        self.alias_map[key] = label

    def lookup(self, text: str) -> Optional[str]:
        if not text:
            return None
        return self.alias_map.get(preprocess(text)) or self.alias_map.get(preprocess_no_accent(text))
