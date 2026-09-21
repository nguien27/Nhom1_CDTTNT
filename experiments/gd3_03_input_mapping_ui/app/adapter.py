from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from experiments.gd3_01_universal_input.src import doc_bytes, doc_chuoi
from experiments.gd3_02_information_mapping.src.output_formatter import format_for_ui
from experiments.gd3_02_information_mapping.src.pipeline import run_pipeline


SUPPORTED_FILE_TYPES = {".csv", ".xlsx", ".docx", ".pdf", ".txt"}

CANONICAL_SOURCE_LABELS = {
    "ma_nhan_vien": "Mã nhân viên",
    "ho_ten": "Họ tên",
    "don_vi": "Đơn vị",
    "loai_don_vi": "Loại đơn vị",
    "chuc_vu": "Chức vụ",
    "email": "Email",
    "extension": "Extension",
}


class InputAnalysisError(ValueError):
    pass


def _raise_upstream_error(contract: Dict[str, Any]) -> None:
    error = contract.get("error")
    if isinstance(error, dict):
        code = error.get("code") or "UPSTREAM_ERROR"
        message = error.get("message") or str(error)
    else:
        code = "UPSTREAM_ERROR"
        message = str(error or "Không thể đọc dữ liệu đầu vào.")

    warnings = contract.get("warnings") or []
    detail = f"{code}: {message}"
    if warnings:
        detail += f"; warnings={warnings}"
    raise InputAnalysisError(detail)


def _structured_table(contract: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], str] | None:
    """Lấy bảng cấu trúc do reader/parser GĐ3-01 đã nhận diện.

    Không suy luận nghiệp vụ ở đây. Giá trị người dùng nhập ở dạng bảng hoặc
    ``Khóa: Giá trị`` được giữ nguyên để tránh Information Extraction làm thay
    đổi nội dung đã có cấu trúc.
    """
    for table in contract.get("tables") or []:
        if not isinstance(table, dict):
            continue
        rows = [row for row in (table.get("rows") or []) if isinstance(row, dict)]
        headers = [str(h) for h in (table.get("headers") or [])]
        if not headers and rows:
            headers = [str(key) for key in rows[0].keys()]
        if not rows or not headers:
            continue
        normalized_rows = [
            {str(key): value for key, value in row.items()}
            for row in rows
        ]
        return headers, normalized_rows, str(table.get("kind") or "structured")
    return None


def _use_direct_structured(
    contract: Dict[str, Any],
    *,
    method: str,
    data_type: str,
    filename: str | None,
) -> bool:
    """Quyết định khi nào giữ nguyên bảng từ reader thay vì qua extractor.

    - Nhập/dán thủ công có cấu trúc phải giữ nguyên giá trị người dùng nhập.
    - Các schema ngoài hồ sơ nhân viên không dùng extractor employee-only.
    - File hồ sơ nhân viên vẫn đi qua pipeline Information Extraction/Schema
      Mapping cũ để giữ tương thích regression; với dữ liệu bảng, pipeline này
      vẫn bảo toàn cell gốc ở ``raw_data.row``.
    """
    table = _structured_table(contract)
    if table is None:
        return False

    kind = table[2].lower()

    if method == "RAW_STRING":
        return kind in {"delimited_text", "key_value"}

    if data_type != "NHAN_VIEN_KHONG_KET_QUA":
        return kind not in {"text", "paragraph", "plain_text"}

    return False


def _prepare_contract_for_gd302(contract: Dict[str, Any]) -> Dict[str, Any]:
    prepared = deepcopy(contract)
    return prepared


def _rows_from_pipeline(payload: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    records = list(payload.get("records") or [])
    if not records:
        return [], []

    source_type = str(
        records[0].get("source_type")
        or payload.get("metadata", {}).get("source_type")
        or ""
    )

    if source_type == "structured":
        rows: List[Dict[str, Any]] = []
        headers: List[str] = []
        for record in records:
            raw_data = record.get("raw_data") or {}
            row = raw_data.get("row")
            if not isinstance(row, dict):
                continue
            normalized_row = {str(k): v for k, v in row.items()}
            for key in normalized_row:
                if key not in headers:
                    headers.append(key)
            rows.append(normalized_row)
        return headers, rows

    present_fields: List[str] = []
    for canonical in CANONICAL_SOURCE_LABELS:
        if any(
            (record.get("data") or {}).get(canonical) not in (None, "")
            for record in records
        ):
            present_fields.append(canonical)

    headers = [CANONICAL_SOURCE_LABELS[field] for field in present_fields]
    rows = []
    for record in records:
        data = record.get("data") or {}
        rows.append({
            CANONICAL_SOURCE_LABELS[field]: data.get(field) or ""
            for field in present_fields
        })
    return headers, rows


def analyze_input(
    content: bytes | None,
    filename: str | None,
    raw_text: str | None,
    input_method: str = "FILE",
    data_type: str = "NHAN_VIEN_KHONG_KET_QUA",
) -> Dict[str, Any]:
    """Đọc input và bảo toàn dữ liệu cấu trúc trước khi mapping.

    - CSV/XLSX và text đã nhận diện bảng/``Khóa: Giá trị``: GĐ3-01 -> Mapping.
    - Văn bản tự do của hồ sơ nhân viên: GĐ3-01 -> GĐ3-02 Information Extraction.
    - Các schema mở rộng không đưa văn bản tự do qua extractor nhân viên.
    """

    method = str(input_method or "FILE").upper()
    data_type = str(data_type or "NHAN_VIEN_KHONG_KET_QUA").strip().upper()
    input_id = f"INP-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if method == "RAW_STRING":
        text = str(raw_text or "").strip()
        if not text:
            raise InputAnalysisError("Nội dung văn bản rỗng. Vui lòng nhập hoặc dán dữ liệu.")
        gd3_01_contract = doc_chuoi(text)
        display_source = "Dữ liệu nhập trực tiếp"
        file_type = "raw_string"
    elif method == "FILE":
        if not content:
            raise InputAnalysisError("Tệp rỗng hoặc không có dữ liệu.")
        name = filename or "uploaded_file"
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_FILE_TYPES:
            supported = ", ".join(sorted(ext.lstrip(".").upper() for ext in SUPPORTED_FILE_TYPES))
            raise InputAnalysisError(
                f"Định dạng tệp không được hỗ trợ: {suffix or '(không có đuôi)'}. Hỗ trợ: {supported}."
            )
        gd3_01_contract = doc_bytes(content, name)
        display_source = name
        file_type = suffix.lstrip(".")
    else:
        raise InputAnalysisError(f"input_method không hợp lệ: {method}")

    if gd3_01_contract.get("status") != "success" or gd3_01_contract.get("error"):
        _raise_upstream_error(gd3_01_contract)

    upstream_meta = dict(gd3_01_contract.get("metadata") or {})

    if _use_direct_structured(
        gd3_01_contract,
        method=method,
        data_type=data_type,
        filename=filename,
    ):
        table = _structured_table(gd3_01_contract)
        assert table is not None
        headers, rows, table_kind = table
        # Giữ contract metadata tương thích các tầng tích hợp cũ. Với hồ sơ
        # nhân viên, Information/Schema Mapping vẫn là tầng chịu trách nhiệm
        # về schema, còn row cấu trúc được giữ nguyên để không sửa giá trị
        # người dùng đã nhập.
        employee_schema = data_type == "NHAN_VIEN_KHONG_KET_QUA"
        metadata = {
            **upstream_meta,
            "input_id": input_id,
            "timestamp": timestamp,
            "display_source": display_source,
            "file_type": file_type,
            "input_method": method,
            "pdf_mode": upstream_meta.get("pdf_mode"),
            "ocr_used": bool(upstream_meta.get("ocr_used")),
            "source_module": (
                "GD3-01 -> GD3-02 -> GD3-03"
                if employee_schema
                else "GD3-01 -> Schema Mapping"
            ),
            "reader_module": "GD3-01",
            "information_mapping_module": (
                "GD3-02" if employee_schema else "Schema Mapping"
            ),
            "source_type": "structured_direct",
            "structured_kind": table_kind,
            "raw_structured_table_detected": True,
        }
        return {
            "headers": headers,
            "rows": rows,
            "preview_rows": rows[:15],
            "metadata": metadata,
            "pipeline_payload": {"metadata": {"source_type": "structured_direct"}, "records": []},
            "structured_direct": True,
            "requires_confirmation": False,
            "confirmation_items": [],
            "upstream_validation": None,
        }

    # Schema mở rộng không được ép qua Information Extraction chỉ dành cho employee.
    if data_type != "NHAN_VIEN_KHONG_KET_QUA":
        raise InputAnalysisError(
            "Loại dữ liệu này cần dữ liệu có cấu trúc (bảng CSV/XLSX/TXT hoặc dạng Khóa: Giá trị)."
        )

    gd3_02_contract = _prepare_contract_for_gd302(gd3_01_contract)
    result = run_pipeline(input_contract=gd3_02_contract)
    payload = format_for_ui(result)

    if not payload.get("records"):
        validation = payload.get("validation") or {}
        errors = validation.get("errors") or []
        message = None
        if errors:
            first = errors[0]
            message = first.get("message") if isinstance(first, dict) else str(first)
        raise InputAnalysisError(message or "Không trích xuất được bản ghi nhân viên từ dữ liệu đầu vào.")

    headers, rows = _rows_from_pipeline(payload)
    if not rows:
        raise InputAnalysisError("Không tạo được dữ liệu xem trước từ kết quả trích xuất.")

    metadata = dict(payload.get("metadata") or {})
    metadata.update(
        {
            "input_id": input_id,
            "timestamp": timestamp,
            "display_source": display_source,
            "file_type": file_type,
            "input_method": method,
            "pdf_mode": upstream_meta.get("pdf_mode") or metadata.get("pdf_mode"),
            "ocr_used": bool(upstream_meta.get("ocr_used") or metadata.get("ocr_used")),
            "source_module": "GD3-01 -> GD3-02 -> GD3-03",
            "reader_module": "GD3-01",
            "information_mapping_module": "GD3-02",
            "raw_structured_table_detected": False,
        }
    )

    return {
        "headers": headers,
        "rows": rows,
        "preview_rows": rows[:15],
        "metadata": metadata,
        "pipeline_payload": payload,
        "structured_direct": False,
        "requires_confirmation": bool(payload.get("requires_confirmation")),
        "confirmation_items": list(payload.get("confirmation_items") or []),
        "upstream_validation": payload.get("validation"),
    }


def process_input(
    content: bytes | None,
    filename: str | None,
    raw_text: str | None,
    input_method: str = "FILE",
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
    analyzed = analyze_input(content, filename, raw_text, input_method)
    return analyzed["headers"], analyzed["rows"], analyzed["metadata"]


def parse_raw_text(text: str) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
    return process_input(None, None, text, "RAW_STRING")
