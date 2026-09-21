"""Output contract cho Backend/UI GĐ3-03."""

from typing import Any, Dict

from .confidence import ConfidenceManager
from .models import ExtractionResult


class OutputFormatter:
    @staticmethod
    def to_backend_payload(result: ExtractionResult) -> Dict[str, Any]:
        validation_ok = bool(result.validation and result.validation.is_valid)
        can_commit = validation_ok and bool(result.records) and not result.requires_user_confirmation

        return {
            "success": bool(result.records),
            "records": [
                {
                    "data": record.get_mapped_dict(),
                    "confidence": dict(record.confidence_scores),
                    "mappings": [mapping.to_dict() for mapping in record.mappings],
                    "source_type": record.source_type,
                    "source_file": record.source_file,
                }
                for record in result.records
            ],
            "validation": result.validation.to_dict() if result.validation else None,
            "requires_confirmation": result.requires_user_confirmation,
            "confirmation_items": list(result.confirmation_items),
            "can_commit": can_commit,
            "metadata": dict(result.metadata),
        }

    @staticmethod
    def to_ui_payload(result: ExtractionResult) -> Dict[str, Any]:
        backend = OutputFormatter.to_backend_payload(result)
        records = []

        for record in result.records:
            mappings = []
            for mapping in record.mappings:
                mappings.append(
                    {
                        **mapping.to_dict(),
                        "confidence_level": ConfidenceManager.get_confidence_level(mapping.confidence),
                    }
                )
            records.append(
                {
                    "data": record.get_mapped_dict(),
                    "confidence": dict(record.confidence_scores),
                    "mappings": mappings,
                    "raw_data": dict(record.raw_data),
                    "source_type": record.source_type,
                    "source_file": record.source_file,
                }
            )

        return {
            **backend,
            "records": records,
            "summary": {
                "total_records": len(result.records),
                "valid_required_records": sum(
                    1
                    for record in result.records
                    if record.ma_nhan_vien and record.ho_ten and record.don_vi
                ),
                "confirmation_count": len(result.confirmation_items),
            },
        }


def format_for_backend(result: ExtractionResult):
    return OutputFormatter.to_backend_payload(result)


def format_for_ui(result: ExtractionResult):
    return OutputFormatter.to_ui_payload(result)
