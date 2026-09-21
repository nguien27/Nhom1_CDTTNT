"""Predictor: Alias Exact Match -> AI -> confidence threshold."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

import joblib

from .alias_mapper import AliasMapper
from .preprocessing import preprocess_no_accent
from .train import INITIAL_CONFIDENCE_THRESHOLD, METADATA_PATH, MODEL_PATH, VALID_LABELS


class SchemaMappingPredictor:
    def __init__(
        self,
        model_path: str | Path = MODEL_PATH,
        threshold: float | None = None,
        alias_path: str | Path | None = None,
    ):
        self.model_path = Path(model_path)
        self.pipeline = None
        self.alias_mapper = AliasMapper(alias_path)
        self.threshold = self._load_threshold() if threshold is None else float(threshold)
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold phải nằm trong [0, 1]")

    def _load_threshold(self) -> float:
        if Path(METADATA_PATH).exists():
            try:
                data = json.loads(Path(METADATA_PATH).read_text(encoding="utf-8"))
                return float(data.get("threshold", INITIAL_CONFIDENCE_THRESHOLD))
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        return INITIAL_CONFIDENCE_THRESHOLD

    def _ensure_model(self) -> None:
        if self.pipeline is None:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Chưa có model tại {self.model_path}. Chạy `python -m src.train` trước."
                )
            self.pipeline = joblib.load(self.model_path)

    def du_doan_truong(self, text: str) -> Dict:
        original = "" if text is None else str(text)

        alias_label = self.alias_mapper.lookup(original)
        if alias_label is not None:
            return {
                "label": alias_label,
                "confidence": 1.0,
                "source": "alias_exact",
                "accepted": True,
                "original_text": original,
            }

        self._ensure_model()
        processed = preprocess_no_accent(original)
        if not processed:
            return {
                "label": "OTHER",
                "confidence": 0.0,
                "source": "ai",
                "accepted": False,
                "original_text": original,
            }

        proba = self.pipeline.predict_proba([processed])[0]
        idx = int(proba.argmax())
        raw_label = str(self.pipeline.classes_[idx])
        confidence = float(proba[idx])
        accepted = confidence >= self.threshold
        label = raw_label if accepted else "OTHER"
        if label not in VALID_LABELS:
            label = "OTHER"
            accepted = False

        return {
            "label": label,
            "confidence": round(confidence, 4),
            "source": "ai",
            "accepted": bool(accepted),
            "original_text": original,
        }

    def du_doan_nhieu(self, columns: Iterable[str]) -> Dict[str, str]:
        return {str(col): self.du_doan_truong(str(col))["label"] for col in columns}

    def du_doan_nhieu_chi_tiet(self, columns: Iterable[str]) -> Dict[str, Dict]:
        return {str(col): self.du_doan_truong(str(col)) for col in columns}

    def map_headers_from_reader_output(self, reader_output: dict) -> Dict[str, str]:
        """Nhận trực tiếp output contract của GĐ2-01 và map tất cả header tìm thấy."""
        if not isinstance(reader_output, dict):
            raise TypeError("reader_output phải là dict")
        if reader_output.get("status") != "success":
            raise ValueError("GĐ2-01 chưa đọc file thành công")

        headers = []
        for block in reader_output.get("du_lieu", []):
            for header in block.get("headers", []) or []:
                if header not in headers:
                    headers.append(header)
        return self.du_doan_nhieu(headers)


_default_predictor: Optional[SchemaMappingPredictor] = None


def du_doan_truong(text: str) -> Dict:
    global _default_predictor
    if _default_predictor is None:
        _default_predictor = SchemaMappingPredictor()
    return _default_predictor.du_doan_truong(text)
