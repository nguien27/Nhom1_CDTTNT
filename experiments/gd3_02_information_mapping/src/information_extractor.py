"""Information Extraction cho text tự do của GĐ3-02."""

from __future__ import annotations

import re
import unicodedata
from typing import List

from .confidence import ConfidenceManager
from .constants import (
    COMMON_POSITIONS,
    EMAIL_PATTERN,
    EMPLOYEE_CODE_PATTERN,
    EXTENSION_PATTERN,
    UNIT_PREFIX_PATTERN,
    UNIT_TYPE_VALUE_ALIASES,
    VIETNAMESE_NAME_PATTERN,
)
from .models import ExtractedField


STOP_FIELD_PATTERN = (
    r"(?=\s*(?:[,;.\n]|(?:loại\s*đơn\s*vị|loai\s*don\s*vi|loại\s*cơ\s*quan|"
    r"loai\s*co\s*quan|loại\s*tổ\s*chức|loai\s*to\s*chuc|unit\s*type|"
    r"chức\s*vụ|chuc\s*vu|chức\s*danh|chuc\s*danh|vị\s*trí|vi\s*tri|"
    r"email|e-mail|extension|ext|máy\s*lẻ|may\s*le)\b)|$)"
)


def _no_accent(text: str) -> str:
    value = str(text or "").strip().lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n,;:.-")


class InformationExtractor:
    def __init__(self, use_ai: bool = False, ai_client=None):
        self.use_ai = bool(use_ai)
        self.ai_client = ai_client

    def split_employee_segments(self, text: str) -> List[str]:
        """Tách nhiều nhân viên theo vị trí các mã có dạng CA018/NV12345/..."""
        normalized = str(text or "").strip()
        if not normalized:
            return []

        matches = list(re.finditer(EMPLOYEE_CODE_PATTERN, normalized, re.IGNORECASE))
        if len(matches) <= 1:
            return [normalized]

        segments: List[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            # Giữ context ngay trước mã ("CBCS mã", "Mã CBCS") nếu nằm cùng câu/ngắn.
            lookback = normalized[max(0, start - 24):start]
            prefix_match = re.search(
                r"(?:CBCS\s+mã|Mã\s+CBCS|Mã\s+NV|MSNV|Mã\s+nhân\s+viên)\s*$",
                lookback,
                re.IGNORECASE,
            )
            if prefix_match:
                start = max(0, match.start() - (len(lookback) - prefix_match.start()))

            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            segment = normalized[start:end].strip(" \t\r\n,;-")
            if segment:
                segments.append(segment)

        return segments

    def extract_records(self, text: str) -> List[List[ExtractedField]]:
        records: List[List[ExtractedField]] = []
        for segment in self.split_employee_segments(text):
            fields = self.extract(segment)
            if any(field.field_name == "ma_nhan_vien" for field in fields):
                records.append(fields)
        return records

    def extract(self, text: str) -> List[ExtractedField]:
        value = str(text or "").strip()
        if not value:
            return []

        fields: List[ExtractedField] = []
        fields.extend(self._extract_employee_code(value))
        fields.extend(self._extract_name(value))
        fields.extend(self._extract_unit(value))
        fields.extend(self._extract_unit_type(value))
        fields.extend(self._extract_position(value))
        fields.extend(self._extract_email(value))
        fields.extend(self._extract_extension(value))

        if self.use_ai and self.ai_client is not None:
            fields.extend(self._extract_with_ai(value))

        fields = self._deduplicate(fields)
        return [ConfidenceManager.apply_to_field(field) for field in fields]

    def _extract_employee_code(self, text: str) -> List[ExtractedField]:
        context_pattern = (
            r"(?:CBCS\s+mã|mã\s*(?:CBCS|cán\s*bộ|nhân\s*viên|NV|CB)|MSNV)"
            r"\s*[:\-]?\s*([A-Za-z]{2,6}\d{2,8})"
        )
        explicit = re.search(context_pattern, text, re.IGNORECASE)
        if explicit:
            return [
                ExtractedField(
                    field_name="ma_nhan_vien",
                    value=explicit.group(1).upper(),
                    confidence=0.98,
                    source_text=explicit.group(0),
                    extraction_method="regex_context",
                )
            ]

        generic = re.search(EMPLOYEE_CODE_PATTERN, text, re.IGNORECASE)
        if generic:
            return [
                ExtractedField(
                    field_name="ma_nhan_vien",
                    value=generic.group(0).upper(),
                    confidence=0.88,
                    source_text=generic.group(0),
                    extraction_method="regex_generic",
                )
            ]
        return []

    def _extract_name(self, text: str) -> List[ExtractedField]:
        """Trích xuất họ tên tiếng Việt, không cho regex ăn sang dòng kế tiếp."""
        results = []

        patterns = [
            (
                r"(?:họ\s*(?:và\s*)?tên|"
                r"tên\s*(?:cán\s*bộ|nhân\s*viên)?)"
                r"\s*[:\-]?\s*("
                + VIETNAMESE_NAME_PATTERN +
                r")"
            ),
            (
                r"(?:CBCS|cán\s*bộ|nhân\s*viên)\s+"
                r"(?!mã\b|ma\b)("
                + VIETNAMESE_NAME_PATTERN +
                r")"
            ),
        ]

        # Quan trọng:
        # xử lý từng dòng riêng để \s+ trong regex tên
        # không thể ăn sang nhãn của dòng kế tiếp.
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        for line in lines:
            for pat in patterns:
                for match in re.finditer(
                    pat,
                    line,
                    re.IGNORECASE,
                ):
                    value = match.group(1).strip()

                    conf = (
                        0.90
                        if re.fullmatch(
                            VIETNAMESE_NAME_PATTERN,
                            value,
                        )
                        else 0.70
                    )

                    results.append(
                        ExtractedField(
                            field_name="ho_ten",
                            value=value,
                            confidence=conf,
                            source_text=match.group(0),
                            extraction_method="rule",
                        )
                    )

        # Fallback:
        # tìm tên cùng dòng với mã nhân viên.
        if not results:
            for line in lines:
                code_match = re.search(
                    EMPLOYEE_CODE_PATTERN,
                    line,
                    re.IGNORECASE,
                )

                if not code_match:
                    continue

                after = line[code_match.end():]

                name_match = re.search(
                    VIETNAMESE_NAME_PATTERN,
                    after,
                )

                if name_match:
                    value = name_match.group(0).strip()

                    results.append(
                        ExtractedField(
                            field_name="ho_ten",
                            value=value,
                            confidence=0.65,
                            source_text=value,
                            extraction_method="rule",
                        )
                    )

                    break

        return results

    def _extract_unit(self, text: str) -> List[ExtractedField]:
        context_pattern = (
            r"(?:công\s*tác\s*tại|cong\s*tac\s*tai|đơn\s*vị(?:\s*công\s*tác)?|don\s*vi(?:\s*cong\s*tac)?|"
            r"thuộc|thuoc)\s*[:\-]?\s*("
            + UNIT_PREFIX_PATTERN
            + r"\s+.+?)"
            + STOP_FIELD_PATTERN
        )
        match = re.search(context_pattern, text, re.IGNORECASE)
        if match:
            return [
                ExtractedField(
                    field_name="don_vi",
                    value=_clean_value(match.group(1)),
                    confidence=0.95,
                    source_text=match.group(0),
                    extraction_method="regex_context",
                )
            ]

        # Không suy đoán đơn vị chỉ từ prefix (ví dụ "Vụ" trong "chức vụ"
        # hoặc "Đội" trong "Đội trưởng") vì dễ tạo false positive.
        return []

    def _extract_unit_type(self, text: str) -> List[ExtractedField]:
        match = re.search(
            r"(?:loại\s*(?:đơn\s*vị|cơ\s*quan|tổ\s*chức)|loai\s*(?:don\s*vi|co\s*quan|to\s*chuc)|unit\s*type)"
            r"\s*[:\-]?\s*([A-Za-zÀ-ỹĐđ_\s]+?)"
            + STOP_FIELD_PATTERN,
            text,
            re.IGNORECASE,
        )
        if not match:
            return []

        raw_value = _clean_value(match.group(1))
        normalized_key = " ".join(_no_accent(raw_value).replace("_", " ").split())
        normalized_value = UNIT_TYPE_VALUE_ALIASES.get(normalized_key)
        if normalized_value is None:
            normalized_value = raw_value.upper().replace(" ", "_")

        return [
            ExtractedField(
                field_name="loai_don_vi",
                value=normalized_value,
                confidence=0.95,
                source_text=match.group(0),
                extraction_method="regex_context",
            )
        ]

    def _extract_position(self, text: str) -> List[ExtractedField]:
        match = re.search(
            r"(?:chức\s*vụ|chuc\s*vu|chức\s*danh|chuc\s*danh|vị\s*trí|vi\s*tri|position)"
            r"\s*[:\-]?\s*([^\n,;.]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return [
                ExtractedField(
                    field_name="chuc_vu",
                    value=_clean_value(match.group(1)),
                    confidence=0.95,
                    source_text=match.group(0),
                    extraction_method="regex_context",
                )
            ]

        for position in COMMON_POSITIONS:
            match = re.search(r"\b" + re.escape(position) + r"\b", text, re.IGNORECASE)
            if match:
                return [
                    ExtractedField(
                        field_name="chuc_vu",
                        value=_clean_value(match.group(0)),
                        confidence=0.88,
                        source_text=match.group(0),
                        extraction_method="dictionary",
                    )
                ]
        return []

    def _extract_email(self, text: str) -> List[ExtractedField]:
        match = re.search(EMAIL_PATTERN, text)
        if not match:
            return []
        return [
            ExtractedField(
                field_name="email",
                value=match.group(0).lower(),
                confidence=0.99,
                source_text=match.group(0),
                extraction_method="regex",
            )
        ]

    def _extract_extension(self, text: str) -> List[ExtractedField]:
        match = re.search(EXTENSION_PATTERN, text, re.IGNORECASE)
        if not match:
            return []
        return [
            ExtractedField(
                field_name="extension",
                value=match.group(1),
                confidence=0.98,
                source_text=match.group(0),
                extraction_method="regex_context",
            )
        ]

    def _extract_with_ai(self, text: str) -> List[ExtractedField]:
        """Hook tùy chọn; AI chỉ extraction, không được đưa ra Business Decision."""
        function = getattr(self.ai_client, "extract_information", None)
        if not callable(function):
            return []
        try:
            result = function(text)
        except Exception:
            return []
        if not isinstance(result, dict):
            return []

        allowed = {
            "ma_nhan_vien", "ho_ten", "don_vi", "loai_don_vi",
            "chuc_vu", "email", "extension",
        }
        fields: List[ExtractedField] = []
        for field_name, raw in result.items():
            if field_name not in allowed or raw in (None, ""):
                continue
            fields.append(
                ExtractedField(
                    field_name=field_name,
                    value=str(raw).strip(),
                    confidence=0.80,
                    extraction_method="ai_optional",
                )
            )
        return fields

    @staticmethod
    def _deduplicate(fields: List[ExtractedField]) -> List[ExtractedField]:
        best: dict[tuple[str, str], ExtractedField] = {}
        for field in fields:
            key = (field.field_name, str(field.value).strip().casefold())
            current = best.get(key)
            if current is None or field.confidence > current.confidence:
                best[key] = field
        return list(best.values())


def extract_information(text: str, use_ai: bool = False, ai_client=None):
    return InformationExtractor(use_ai=use_ai, ai_client=ai_client).extract(text)
