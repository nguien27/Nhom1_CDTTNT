"""Quản lý confidence và danh sách cần Human Confirmation."""

from typing import Dict, Iterable, List

from .constants import CONFIDENCE_THRESHOLDS, CONFIRMATION_THRESHOLD
from .models import ExtractedField, MappingCandidate


class ConfidenceManager:
    @staticmethod
    def normalize_score(score: float) -> float:
        value = float(score or 0.0)
        if value > 1.0:
            value = value / 100.0
        return max(0.0, min(1.0, value))

    @classmethod
    def get_confidence_level(cls, score: float) -> str:
        value = cls.normalize_score(score)
        if value >= CONFIDENCE_THRESHOLDS["high"]:
            return "high"
        if value >= CONFIDENCE_THRESHOLDS["medium"]:
            return "medium"
        if value >= CONFIDENCE_THRESHOLDS["low"]:
            return "low"
        return "very_low"

    @classmethod
    def requires_confirmation(cls, score: float) -> bool:
        return cls.normalize_score(score) < CONFIRMATION_THRESHOLD

    @classmethod
    def aggregate_confidence(cls, scores: Iterable[float]) -> float:
        values = [cls.normalize_score(score) for score in scores]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    @classmethod
    def apply_to_mapping(cls, mapping: MappingCandidate) -> MappingCandidate:
        mapping.confidence = cls.normalize_score(mapping.confidence)
        mapping.requires_confirmation = (
            not mapping.accepted
            or mapping.target is None
            or cls.requires_confirmation(mapping.confidence)
        )
        return mapping

    @classmethod
    def apply_to_field(cls, field: ExtractedField) -> ExtractedField:
        field.confidence = cls.normalize_score(field.confidence)
        field.requires_confirmation = cls.requires_confirmation(field.confidence)
        return field

    @classmethod
    def get_confirmation_items(
        cls,
        mappings: List[MappingCandidate],
        record_index: int | None = None,
    ) -> List[Dict]:
        items: List[Dict] = []
        for mapping in mappings:
            mapping = cls.apply_to_mapping(mapping)
            if not mapping.requires_confirmation:
                continue
            item = {
                "source": mapping.source,
                "target": mapping.target,
                "raw_value": mapping.raw_value,
                "confidence": mapping.confidence,
                "level": cls.get_confidence_level(mapping.confidence),
                "requires_confirmation": True,
                "accepted": mapping.accepted,
                "source_method": mapping.source_method,
                "note": mapping.note,
            }
            if record_index is not None:
                item["record_index"] = record_index
            items.append(item)
        return items


def calculate_confidence(field_scores: List[float]) -> float:
    return ConfidenceManager.aggregate_confidence(field_scores)
