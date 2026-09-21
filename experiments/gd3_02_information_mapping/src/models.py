"""Data models thống nhất cho GĐ3-02."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MappingCandidate:
    source: str
    target: Optional[str]
    confidence: float
    requires_confirmation: bool = False
    raw_value: Optional[str] = None
    note: Optional[str] = None
    source_method: str = "unknown"
    accepted: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedField:
    field_name: str
    value: str
    confidence: float
    source_text: Optional[str] = None
    extraction_method: str = "rule"
    requires_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmployeeRecord:
    ma_nhan_vien: Optional[str] = None
    ho_ten: Optional[str] = None
    don_vi: Optional[str] = None
    loai_don_vi: Optional[str] = None
    chuc_vu: Optional[str] = None
    email: Optional[str] = None
    extension: Optional[str] = None

    confidence_scores: Dict[str, float] = field(default_factory=dict)
    mappings: List[MappingCandidate] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "unknown"
    source_file: Optional[str] = None

    def get_mapped_dict(self) -> Dict[str, Optional[str]]:
        return {
            "ma_nhan_vien": self.ma_nhan_vien,
            "ho_ten": self.ho_ten,
            "don_vi": self.don_vi,
            "loai_don_vi": self.loai_don_vi,
            "chuc_vu": self.chuc_vu,
            "email": self.email,
            "extension": self.extension,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.get_mapped_dict(),
            "confidence_scores": dict(self.confidence_scores),
            "mappings": [item.to_dict() for item in self.mappings],
            "raw_data": dict(self.raw_data),
            "source_type": self.source_type,
            "source_file": self.source_file,
        }


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, code: str, message: str, **extra: Any) -> None:
        self.errors.append({"code": code, "message": message, **extra})
        self.is_valid = False

    def add_warning(self, code: str, message: str, **extra: Any) -> None:
        self.warnings.append({"code": code, "message": message, **extra})

    @property
    def error_codes(self) -> List[str]:
        return list(dict.fromkeys(item["code"] for item in self.errors))

    @property
    def warning_codes(self) -> List[str]:
        return list(dict.fromkeys(item["code"] for item in self.warnings))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "error_codes": self.error_codes,
            "warning_codes": self.warning_codes,
            "details": dict(self.details),
        }


@dataclass
class ExtractionResult:
    records: List[EmployeeRecord] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    requires_user_confirmation: bool = False
    confirmation_items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
            "validation": self.validation.to_dict() if self.validation else None,
            "metadata": dict(self.metadata),
            "requires_user_confirmation": self.requires_user_confirmation,
            "confirmation_items": list(self.confirmation_items),
        }
