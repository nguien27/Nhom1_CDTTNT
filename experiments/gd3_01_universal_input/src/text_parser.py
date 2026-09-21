from __future__ import annotations

import csv
import io
import re
from typing import Any


KEY_VALUE_PATTERN = re.compile(r"^\s*([^:=]{1,100}?)\s*[:=]\s*(.*?)\s*$")


def normalize_text(value: str) -> str:
    value = str(value).replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return "\n".join(line.rstrip() for line in value.split("\n")).strip()


def _unique_headers(headers: list[str]) -> list[str]:
    output: list[str] = []
    counts: dict[str, int] = {}
    for index, raw in enumerate(headers, 1):
        name = str(raw).strip() or f"Column_{index}"
        if name in counts:
            counts[name] += 1
            name = f"{name}_{counts[name]}"
        else:
            counts[name] = 0
        while name in output:
            counts[name] = counts.get(name, 0) + 1
            name = f"{name}_{counts[name]}"
        output.append(name)
    return output


def _parse_delimited(text: str, name: str) -> dict[str, Any] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    sample = "\n".join(lines[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=["\t", ";", ",", "|"])
        parsed = list(csv.reader(io.StringIO(text), dialect=dialect))
    except csv.Error:
        return None
    parsed = [[str(cell).strip() for cell in row] for row in parsed if any(str(c).strip() for c in row)]
    if len(parsed) < 2 or len(parsed[0]) < 2:
        return None
    width = len(parsed[0])
    if any(len(row) != width for row in parsed[1:]):
        return None
    headers = _unique_headers(parsed[0])
    return {
        "name": name,
        "headers": headers,
        "rows": [dict(zip(headers, row)) for row in parsed[1:]],
        "kind": "delimited_text",
    }


def _parse_key_value(text: str, name: str) -> dict[str, Any] | None:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    matched = 0
    nonempty = 0

    # Hỗ trợ cách nhập nhanh trên một dòng:
    # ``Mã CBCS: NV001; Họ tên: Nguyễn Văn A; Đơn vị: Cục Đào tạo``.
    # Chỉ tách theo dấu chấm phẩy khi *mọi* đoạn đều có dạng Khóa: Giá trị,
    # nhờ vậy dấu ';' nằm trong một giá trị tự do vẫn được giữ nguyên.
    logical_lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            logical_lines.append(raw_line)
            continue
        parts = [part.strip() for part in raw_line.split(";") if part.strip()]
        if len(parts) > 1 and all(KEY_VALUE_PATTERN.match(part) for part in parts):
            logical_lines.extend(parts)
        else:
            logical_lines.append(raw_line)

    for line in logical_lines:
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        nonempty += 1
        match = KEY_VALUE_PATTERN.match(line)
        if not match:
            continue
        matched += 1
        key, value = match.group(1).strip(), match.group(2).strip()
        if key in current:
            records.append(current)
            current = {}
        current[key] = value
    if current:
        records.append(current)
    # Chấp nhận cả bản ghi chỉ có một trường, ví dụ nhập thủ công đơn vị:
    # ``Tên đơn vị: Cục Đào tạo``.  Ngưỡng cũ yêu cầu >=2 cặp khóa/giá trị
    # khiến loại DON_VI một trường không thể đi qua parser.
    min_expected = max(1, (nonempty + 1) // 2)
    if not records or matched < 1 or matched < min_expected:
        return None
    headers: list[str] = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)
    return {
        "name": name,
        "headers": headers,
        "rows": [{header: record.get(header, "") for header in headers} for record in records],
        "kind": "key_value",
    }


def parse_text_tables(text: str, name: str = "Text_1") -> list[dict[str, Any]]:
    """Nhận diện bảng phân cách hoặc các dòng Khóa: Giá trị; không suy luận nghiệp vụ."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    delimited = _parse_delimited(normalized, name)
    if delimited:
        return [delimited]
    key_value = _parse_key_value(normalized, name)
    return [key_value] if key_value else []

