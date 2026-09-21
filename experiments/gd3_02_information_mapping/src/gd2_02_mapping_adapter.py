"""Adapter trực tiếp tới GĐ2-02 AI Schema Mapping.

GĐ2-02 là mapper nền tảng cho các nhãn mà model đã được huấn luyện.
Ba field mở rộng của GĐ3-02 (chuc_vu, email, extension) dùng alias xác định
vì model GĐ2-02 hiện không có ba class này. Không fallback về GĐ1-03.
"""

from __future__ import annotations

import importlib
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from .confidence import ConfidenceManager
from .constants import (
    FIELD_ALIASES,
    GD2_02_SUPPORTED_LABELS,
    MIN_MAPPING_CONFIDENCE,
    STANDARD_FIELDS,
)
from .models import ExtractedField, MappingCandidate


LOCAL_ONLY_FIELDS = {"chuc_vu", "email", "extension"}


def _normalize_text(text: Any) -> str:
    value = str(text or "").strip().lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    for char in ("_", "-", ".", "/"):
        value = value.replace(char, " ")
    return " ".join(value.split())


def _normalized_alias_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for target, aliases in FIELD_ALIASES.items():
        for alias in [target, *aliases]:
            key = _normalize_text(alias)
            if key and key not in mapping:
                mapping[key] = target
    return mapping


LOCAL_ALIAS_MAP = _normalized_alias_map()


class GD202AdapterError(RuntimeError):
    pass


def _find_project_root() -> Path:
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if (candidate / "experiments" / "gd2_02_ai_schema_mapping" / "src" / "predict.py").is_file():
            return candidate

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "experiments" / "gd2_02_ai_schema_mapping" / "src" / "predict.py"
        if candidate.is_file():
            return parent

    raise GD202AdapterError(
        "Không tìm thấy experiments/gd2_02_ai_schema_mapping. "
        "Hãy đặt GĐ3-02 cùng repo với GĐ2-02 hoặc cấu hình PROJECT_ROOT."
    )


def _load_predictor_class():
    project_root = _find_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    module = importlib.import_module("experiments.gd2_02_ai_schema_mapping.src.predict")
    predictor_class = getattr(module, "SchemaMappingPredictor", None)
    if predictor_class is None:
        raise GD202AdapterError("GĐ2-02 không export SchemaMappingPredictor.")
    return predictor_class, project_root


class GD202SchemaMappingAdapter:
    def __init__(self):
        self.predictor = None
        self.predictor_error: Optional[str] = None
        self.project_root: Optional[Path] = None
        self._load_predictor()

    @property
    def upstream_available(self) -> bool:
        return self.predictor is not None

    def _load_predictor(self) -> None:
        try:
            predictor_class, project_root = _load_predictor_class()
            self.project_root = project_root
            alias_path = project_root / "config" / "field_aliases.json"
            if alias_path.is_file():
                self.predictor = predictor_class(alias_path=alias_path)
            else:
                self.predictor = predictor_class()
        except Exception as exc:
            self.predictor = None
            self.predictor_error = str(exc)

    @staticmethod
    def _local_exact(header: str, only_fields: set[str] | None = None) -> Optional[MappingCandidate]:
        target = LOCAL_ALIAS_MAP.get(_normalize_text(header))
        if target is None or (only_fields is not None and target not in only_fields):
            return None
        return ConfidenceManager.apply_to_mapping(
            MappingCandidate(
                source=str(header),
                target=target,
                confidence=0.98,
                source_method="gd3_02_alias_exact",
                accepted=True,
                note="Alias xác định cho schema GĐ3-02.",
            )
        )

    @staticmethod
    def _local_fuzzy(header: str) -> Optional[MappingCandidate]:
        source = _normalize_text(header)
        if not source:
            return None
        best_target = None
        best_score = 0.0
        for alias, target in LOCAL_ALIAS_MAP.items():
            if source == alias:
                score = 0.98
            elif source in alias or alias in source:
                ratio = min(len(source), len(alias)) / max(len(source), len(alias))
                score = 0.65 + 0.19 * ratio
            else:
                continue
            if score > best_score:
                best_target = target
                best_score = score
        if best_target is None or best_score < MIN_MAPPING_CONFIDENCE:
            return None
        return ConfidenceManager.apply_to_mapping(
            MappingCandidate(
                source=str(header),
                target=best_target,
                confidence=round(best_score, 4),
                source_method="gd3_02_alias_fuzzy",
                accepted=True,
                note="Fallback alias; cần xác nhận nếu confidence < 0.85.",
            )
        )

    def _predict_upstream(self, header: str) -> Optional[MappingCandidate]:
        if self.predictor is None:
            return None
        try:
            result = self.predictor.du_doan_truong(str(header))
        except Exception as exc:
            self.predictor_error = str(exc)
            return None

        label = str(result.get("label") or "OTHER")
        target = GD2_02_SUPPORTED_LABELS.get(label)
        score = ConfidenceManager.normalize_score(result.get("confidence", 0.0))
        accepted = bool(result.get("accepted")) and target in STANDARD_FIELDS

        if label == "OTHER" or target is None:
            return None

        return ConfidenceManager.apply_to_mapping(
            MappingCandidate(
                source=str(header),
                target=target,
                confidence=score,
                source_method=f"gd2_02:{result.get('source', 'unknown')}",
                accepted=accepted,
                note=f"GĐ2-02 label={label}",
            )
        )

    def predict_column(self, header: str) -> MappingCandidate:
        raw = str(header or "").strip()

        # GĐ2-02 không có class cho ba field này; exact alias phải chặn AI đoán nhầm.
        local_only = self._local_exact(raw, only_fields=LOCAL_ONLY_FIELDS)
        if local_only is not None:
            return local_only

        upstream = self._predict_upstream(raw)
        local_exact = self._local_exact(raw)

        # Alias được Leader/GĐ3-02 khai báo rõ có thể củng cố kết quả GĐ2-02.
        # Điều này đặc biệt hữu ích với alias hợp lệ nhưng model GĐ2-02 chỉ cho
        # confidence trung bình. Nếu AI và alias đồng thuận, dùng exact confidence.
        if upstream is not None and local_exact is not None:
            if upstream.target == local_exact.target:
                local_exact.source_method = f"{upstream.source_method}+gd3_02_alias_exact"
                local_exact.note = "GĐ2-02 và alias GĐ3-02 đồng thuận."
                return local_exact
            # Alias exact có độ xác định cao hơn một dự đoán AI khác nghĩa.
            local_exact.source_method = f"gd3_02_alias_exact_after_{upstream.source_method}"
            local_exact.note = "Alias exact được ưu tiên khi dự đoán AI không đồng thuận."
            return local_exact

        if upstream is not None:
            return upstream

        if local_exact is not None:
            return local_exact

        local_fuzzy = self._local_fuzzy(raw)
        if local_fuzzy is not None:
            return local_fuzzy

        return ConfidenceManager.apply_to_mapping(
            MappingCandidate(
                source=raw,
                target=None,
                confidence=0.0,
                source_method="unknown",
                accepted=False,
                note="Không xác định được schema; cần người dùng chọn field hoặc bỏ qua.",
            )
        )

    def map_headers(self, headers: List[str]) -> List[MappingCandidate]:
        return [self.predict_column(header) for header in headers]

    def map_extracted_fields(self, fields: List[ExtractedField]) -> List[MappingCandidate]:
        """IE đã gắn canonical field_name; adapter giữ contract mapping thống nhất."""
        mappings: List[MappingCandidate] = []
        for field in fields:
            if field.field_name not in STANDARD_FIELDS:
                continue
            mappings.append(
                ConfidenceManager.apply_to_mapping(
                    MappingCandidate(
                        source=field.source_text or field.field_name,
                        target=field.field_name,
                        confidence=field.confidence,
                        raw_value=field.value,
                        source_method=f"information_extraction:{field.extraction_method}",
                        accepted=True,
                        note="Field đã được Information Extraction xác định semantic.",
                    )
                )
            )
        return mappings


def map_headers(headers: List[str]) -> List[MappingCandidate]:
    return GD202SchemaMappingAdapter().map_headers(headers)
