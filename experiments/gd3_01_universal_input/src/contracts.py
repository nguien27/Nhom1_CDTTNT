from __future__ import annotations

from typing import Any


def success_contract(source_type: str, **metadata: Any) -> dict[str, Any]:
    """Tạo contract thành công thống nhất cho mọi nguồn đầu vào."""
    return {
        "status": "success",
        "source_type": source_type,
        "text": "",
        "tables": [],
        "pages": [],
        "metadata": dict(metadata),
        "warnings": [],
        "error": None,
    }


def error_contract(
    source_type: str,
    code: str,
    message: str,
    *,
    warnings: list[str] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    """Lỗi là dữ liệu trả về, không phát tán exception lên Backend."""
    result = success_contract(source_type, **metadata)
    result["status"] = "error"
    result["warnings"] = list(warnings or [])
    result["error"] = {"code": code, "message": message}
    return result


def table_to_text(table: dict[str, Any]) -> str:
    headers = [str(value) for value in table.get("headers", [])]
    lines: list[str] = []
    if headers:
        lines.append("\t".join(headers))
    for row in table.get("rows", []):
        if isinstance(row, dict):
            lines.append("\t".join(str(row.get(header, "")) for header in headers))
    return "\n".join(lines).strip()


def finalize_contract(result: dict[str, Any]) -> dict[str, Any]:
    """Bổ sung thống kê nhất quán mà không làm thay đổi dữ liệu đã đọc."""
    metadata = result.setdefault("metadata", {})
    tables = result.setdefault("tables", [])
    pages = result.setdefault("pages", [])
    metadata["table_count"] = len(tables)
    metadata["page_count"] = len(pages)
    metadata["row_count"] = sum(len(table.get("rows", [])) for table in tables)
    metadata["character_count"] = len(result.get("text", ""))
    metadata.setdefault("contract_version", "gd3-01.v1")
    return result

