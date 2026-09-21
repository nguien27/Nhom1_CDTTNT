from __future__ import annotations
import csv
from datetime import datetime
import io
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Re-use GĐ2-04 database and search-rule bridges
from experiments.gd2_04_backend_upload_ui.app.database import DEFAULT_DB_PATH, ensure_database, get_connection
from experiments.gd2_04_backend_upload_ui.app.integration.search_rule_bridge import SearchRuleBridge
from experiments.gd2_04_backend_upload_ui.app.upload_service import preview_upload as gd2_preview_upload, commit_upload as gd2_commit_upload

# GĐ3-03 services
from .adapter import InputAnalysisError, analyze_input
from .mapping_service import MappingService
from .validation_service import ValidationService
from .commit_service import CommitService

APP_DIR = Path(__file__).resolve().parent
GD3_DIR = APP_DIR.parent
TEMPLATES = Jinja2Templates(directory=str(GD3_DIR / "templates"))
SEARCH_HISTORY: List[Dict[str, Any]] = []


def _row_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _item_contract(conn: sqlite3.Connection, item: Dict[str, Any]) -> Dict[str, Any]:
    bridge = SearchRuleBridge(conn)
    kind = item.get("loai_doi_tuong")
    if kind == "NHAN_VIEN":
        ma = item.get("ma_nhan_vien") or item.get("id_doi_tuong")
        status = bridge.employee_status(str(ma))
        doi_tuong = {
            "id": item.get("id"), "ma_nhan_vien": ma, "ho_ten": item.get("ho_ten"),
            "ma_don_vi": item.get("ma_don_vi"), "don_vi": item.get("don_vi") or item.get("ten_don_vi"),
            "ten_don_vi": item.get("ten_don_vi") or item.get("don_vi"),
            "chuc_vu": item.get("chuc_vu"), "email": item.get("email"),
        }
        name = item.get("ho_ten")
    else:
        ma = item.get("ma_don_vi") or item.get("id_doi_tuong")
        status = bridge.unit_status(str(ma))
        doi_tuong = {
            "id": item.get("id"), "ma_don_vi": ma, "ten_don_vi": item.get("ten_don_vi"),
            "loai_don_vi": item.get("loai_don_vi"),
        }
        name = item.get("ten_don_vi")
    return {
        "doi_tuong": doi_tuong,
        "loai_doi_tuong": kind,
        "id_doi_tuong": ma,
        "ten_hien_thi": name,
        "do_khop": item.get("do_khop"),
        "loai_khop": item.get("loai_khop"),
        "trang_thai_tra_luong": status,
    }


def create_app(db_path: str | Path | None = None) -> FastAPI:
    db_path = Path(db_path or DEFAULT_DB_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = ensure_database(db_path)
        conn.close()
        yield

    app = FastAPI(title="PayrollCheck GĐ3-03 Input Mapping UI", version="3.3.0", lifespan=lifespan)
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=str(GD3_DIR / "static")), name="static")

    def conn_now():
        return get_connection(app.state.db_path)

    # -------------------------------------------------------------
    # 1. UI Root
    # -------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return TEMPLATES.TemplateResponse(request, "index.html")

    # -------------------------------------------------------------
    # 2. GĐ3-03 API Endpoints
    # -------------------------------------------------------------
    mapping_svc = MappingService()
    validation_svc = ValidationService()

    @app.post("/api/v1/input/analyze-file")
    async def analyze_file(
        file: UploadFile = File(...),
        data_type: str = Form("NHAN_VIEN_KHONG_KET_QUA")
    ):
        content = await file.read()
        if not content:
            raise HTTPException(400, "Tệp rỗng hoặc không có dữ liệu. Vui lòng chọn tệp hợp lệ.")

        try:
            analyzed = analyze_input(content, file.filename or "upload.csv", None, "FILE", data_type)
            headers = analyzed["headers"]
            rows = analyzed["rows"]
            mapping_result = (
                mapping_svc.generate_mapping(headers, rows[:10], data_type)
                if analyzed.get("structured_direct")
                else mapping_svc.generate_from_pipeline(
                    analyzed["pipeline_payload"], headers, rows[:10], data_type
                )
            )
            return {
                "ok": True,
                "input_method": "FILE",
                "filename": file.filename or "upload.csv",
                "metadata": analyzed["metadata"],
                "data_type": data_type,
                "headers": headers,
                "so_dong": len(rows),
                "rows": rows,
                "preview_rows": analyzed["preview_rows"],
                "mapping_items": mapping_result["mapping_items"],
                "duplicates": mapping_result["duplicates"],
                "missing_fields": mapping_result["missing_fields"],
                "pending_confirmation": mapping_result["pending_confirmation"],
                "schema_options": mapping_result["schema_options"],
                "requires_confirmation": analyzed["requires_confirmation"],
                "confirmation_items": analyzed["confirmation_items"],
                "upstream_validation": analyzed["upstream_validation"],
                "pipeline_modules": {"reader": "GD3-01", "information_mapping": "GD3-02"},
            }
        except InputAnalysisError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/input/analyze-text")
    async def analyze_text(payload: Dict[str, Any] = Body(...)):
        raw_text = payload.get("raw_text", "")
        data_type = payload.get("data_type", "NHAN_VIEN_KHONG_KET_QUA")

        if not raw_text or not raw_text.strip():
            raise HTTPException(400, "Vui lòng nhập hoặc dán nội dung văn bản.")

        try:
            analyzed = analyze_input(None, None, raw_text, "RAW_STRING", data_type)
            headers = analyzed["headers"]
            rows = analyzed["rows"]
            mapping_result = (
                mapping_svc.generate_mapping(headers, rows[:10], data_type)
                if analyzed.get("structured_direct")
                else mapping_svc.generate_from_pipeline(
                    analyzed["pipeline_payload"], headers, rows[:10], data_type
                )
            )
            return {
                "ok": True,
                "input_method": "RAW_STRING",
                "filename": "Văn bản dán trực tiếp",
                "metadata": analyzed["metadata"],
                "data_type": data_type,
                "headers": headers,
                "so_dong": len(rows),
                "rows": rows,
                "preview_rows": analyzed["preview_rows"],
                "mapping_items": mapping_result["mapping_items"],
                "duplicates": mapping_result["duplicates"],
                "missing_fields": mapping_result["missing_fields"],
                "pending_confirmation": mapping_result["pending_confirmation"],
                "schema_options": mapping_result["schema_options"],
                "requires_confirmation": analyzed["requires_confirmation"],
                "confirmation_items": analyzed["confirmation_items"],
                "upstream_validation": analyzed["upstream_validation"],
                "pipeline_modules": {"reader": "GD3-01", "information_mapping": "GD3-02"},
            }
        except InputAnalysisError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/input/validate")
    async def validate_data(payload: Dict[str, Any] = Body(...)):
        rows = payload.get("rows", [])
        mapping_items = payload.get("mapping_items", [])
        data_type = str(payload.get("data_type") or "NHAN_VIEN_KHONG_KET_QUA").strip().upper()

        if not rows:
            raise HTTPException(400, "Không có dữ liệu để kiểm tra.")
        if not mapping_items:
            raise HTTPException(400, "Thiếu cấu hình ánh xạ trường dữ liệu.")

        result = validation_svc.validate_dataset(rows, mapping_items, data_type)
        return result

    @app.post("/api/v1/input/commit")
    async def commit_data(payload: Dict[str, Any] = Body(...)):
        rows = payload.get("rows", [])
        mapping_items = payload.get("mapping_items", [])
        data_type = str(payload.get("data_type") or "NHAN_VIEN_KHONG_KET_QUA").strip().upper()
        mode = payload.get("mode", "APPEND").upper()

        if not rows:
            raise HTTPException(400, "Không có dữ liệu để commit.")

        # Bắt buộc kiểm tra Validation trước khi cho phép Commit
        val_res = validation_svc.validate_dataset(rows, mapping_items, data_type)
        if not val_res.get("can_commit"):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Không thể Commit khi kiểm tra dữ liệu không đạt (Validation FAIL).",
                    "validation_result": val_res
                }
            )

        conn = conn_now()
        try:
            result = CommitService.commit_dataset(conn, rows, mapping_items, data_type, mode)
            return result
        except Exception as exc:
            raise HTTPException(500, f"Lỗi commit cơ sở dữ liệu: {exc}") from exc
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 3. GĐ2-04 Compatibility Endpoints
    # -------------------------------------------------------------
    @app.post("/upload/preview")
    async def upload_preview(file: UploadFile = File(...), data_type: str = Query(...)):
        content = await file.read()
        if not content:
            raise HTTPException(400, "File rỗng")
        try:
            return gd2_preview_upload(content, file.filename or "upload.csv", data_type)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/upload/commit")
    async def upload_commit(file: UploadFile = File(...), data_type: str = Query(...), mode: str = Query("APPEND")):
        content = await file.read()
        if not content:
            raise HTTPException(400, "File rỗng")
        conn = conn_now()
        try:
            result = gd2_commit_upload(conn, content, file.filename or "upload.csv", data_type, mode)
            if not result.get("ok"):
                raise HTTPException(422, detail=result)
            return result
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 4. Search & Rule Engine Endpoints (No hardcoding)
    # -------------------------------------------------------------
    @app.get("/search")
    def search(
        q: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        page: Optional[int] = Query(None, ge=1)
    ):
        conn = conn_now()
        try:
            actual_offset = (page - 1) * limit if page is not None else offset
            bridge = SearchRuleBridge(conn)
            raw = bridge.search(q, limit=limit, offset=actual_offset)
            items = [_item_contract(conn, x) for x in raw["ket_qua"]]
            total = raw["tong_ket_qua"]
            current_page = page if page is not None else actual_offset // limit + 1
            SEARCH_HISTORY.append({
                "query_id": f"QRY-{len(SEARCH_HISTORY)+1:04d}",
                "query": q,
                "object_name": items[0]["ten_hien_thi"] if items else "Không tìm thấy",
                "object_type": items[0]["loai_doi_tuong"] if items else "-",
                "result": items[0]["trang_thai_tra_luong"]["ket_qua"] if items else "CHUA_XAC_DINH",
                "rule": items[0]["trang_thai_tra_luong"].get("ma_quy_tac") if items else None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user": "Quản trị viên",
            })
            return {
                "query": q, "tong_ket_qua": total, "limit": limit,
                "offset": actual_offset, "page": current_page,
                "total_pages": max(1, (total + limit - 1) // limit),
                "ket_qua": items
            }
        finally:
            conn.close()

    @app.get("/employees/{employee_id}")
    def employee_detail(employee_id: int):
        conn = conn_now()
        try:
            row = conn.execute("SELECT * FROM nhan_vien WHERE id=?", (employee_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy nhân viên")
            status = SearchRuleBridge(conn).employee_status(row["ma_nhan_vien"])
            return {"doi_tuong": _row_dict(row), "trang_thai_tra_luong": status}
        finally:
            conn.close()

    @app.get("/payroll-status/employee/{employee_id}")
    def employee_payroll(employee_id: int):
        return employee_detail(employee_id)

    @app.get("/units/{unit_id}")
    def unit_detail(unit_id: int):
        conn = conn_now()
        try:
            row = conn.execute("SELECT * FROM don_vi WHERE id=?", (unit_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy đơn vị")
            status = SearchRuleBridge(conn).unit_status(row["ma_don_vi"])
            return {"doi_tuong": _row_dict(row), "trang_thai_tra_luong": status}
        finally:
            conn.close()

    @app.get("/payroll-status/unit/{unit_id}")
    def unit_payroll(unit_id: int):
        return unit_detail(unit_id)

    # -------------------------------------------------------------
    # 5. Queries for Dashboard & Database Explorer
    # -------------------------------------------------------------
    @app.get("/health")
    def health():
        conn = conn_now()
        try:
            return {
                "status": "ok",
                "version": "3.3.0",
                "module": "GD3-03",
                "nhan_vien": conn.execute("SELECT COUNT(*) FROM nhan_vien").fetchone()[0],
                "business_rule": conn.execute("SELECT COUNT(*) FROM business_rule").fetchone()[0],
                "ngoai_le_ca_nhan": conn.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0],
                "don_vi_nguon": conn.execute("SELECT COUNT(*) FROM don_vi_nguon").fetchone()[0],
                "gd3_01_universal_input": True, "gd3_02_information_mapping": True,
                "gd2_03_search_engine": True, "gd2_03_rule_engine": True,
                "gd2_04_database_backend": True, "gd3_03_input_mapping_ui": True,
            }
        finally:
            conn.close()

    @app.get("/api/employees")
    def api_employees(page: int = 1, limit: int = 20, search: Optional[str] = None):
        conn = conn_now()
        try:
            offset = (page - 1) * limit
            if search:
                p = f"%{search}%"
                where = "WHERE ma_nhan_vien LIKE ? OR ho_ten LIKE ? OR don_vi LIKE ?"
                params = (p, p, p)
            else:
                where = ""
                params = ()
            total = conn.execute(f"SELECT COUNT(*) FROM nhan_vien {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM nhan_vien {where} ORDER BY id LIMIT ? OFFSET ?", params + (limit, offset)).fetchall()
            bridge = SearchRuleBridge(conn)
            return {
                "total": total, "page": page, "limit": limit,
                "total_pages": max(1, (total + limit - 1) // limit),
                "employees": [{**_row_dict(r), "trang_thai_tra_luong": bridge.employee_status(r["ma_nhan_vien"])} for r in rows]
            }
        finally:
            conn.close()

    @app.get("/api/units")
    def api_units():
        conn = conn_now()
        try:
            bridge = SearchRuleBridge(conn)
            rows = conn.execute("SELECT * FROM don_vi ORDER BY ten_don_vi_chuan").fetchall()
            return {
                "units": [
                    {
                        **_row_dict(r),
                        "employee_count": conn.execute("SELECT COUNT(*) FROM nhan_vien WHERE ma_don_vi=?", (r["ma_don_vi"],)).fetchone()[0],
                        "trang_thai_tra_luong": bridge.unit_status(r["ma_don_vi"])
                    }
                    for r in rows
                ]
            }
        finally:
            conn.close()

    @app.get("/api/rules")
    def api_rules():
        conn = conn_now()
        try:
            return {"rules": [_row_dict(r) for r in conn.execute("SELECT * FROM business_rule ORDER BY muc_uu_tien DESC, id DESC").fetchall()]}
        finally:
            conn.close()

    @app.get("/api/exceptions")
    def api_exceptions():
        conn = conn_now()
        try:
            return {"exceptions": [_row_dict(r) for r in conn.execute("SELECT * FROM ngoai_le_ca_nhan ORDER BY muc_uu_tien DESC, id DESC").fetchall()]}
        finally:
            conn.close()

    @app.get("/api/history")
    def api_history():
        return {"history": list(reversed(SEARCH_HISTORY[-30:]))}

    @app.get("/api/dashboard/stats")
    def dashboard_stats():
        conn = conn_now()
        try:
            total_nv = conn.execute("SELECT COUNT(*) FROM nhan_vien").fetchone()[0]
            bridge = SearchRuleBridge(conn)
            yes = no = undef = 0
            for r in conn.execute("SELECT ma_nhan_vien FROM nhan_vien LIMIT 100").fetchall():
                k = bridge.employee_status(r["ma_nhan_vien"])["ket_qua"]
                yes += (k == "YES")
                no += (k == "NO")
                undef += (k == "CHUA_XAC_DINH")
            return {
                "total_employees": total_nv,
                "total_units": conn.execute("SELECT COUNT(*) FROM don_vi").fetchone()[0],
                "total_rules": conn.execute("SELECT COUNT(*) FROM business_rule").fetchone()[0],
                "total_exceptions": conn.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0],
                "count_yes": yes, "count_no": no, "count_unidentified": undef
            }
        finally:
            conn.close()

    @app.get("/api/system")
    def system_info():
        import socket
        return {
            "server_status": "ONLINE",
            "database_status": "CONNECTED",
            "search_engine": "GD2-03",
            "rule_engine": "GD2-03",
            "ocr_engine": "GD3-01 (reuse GĐ2-01)",
            "input_adapter": "GD3-01 Universal Input via GĐ3-03 adapter",
            "mapping_engine": "GD3-02 Information Extraction + GĐ2-02 Schema Mapping",
            "version": "3.3.0",
            "host_name": socket.gethostname(),
            "port": 8000
        }

    @app.get("/export/search")
    def export_search(q: str = Query(..., min_length=1), format: str = Query("csv")):
        conn = conn_now()
        try:
            raw = SearchRuleBridge(conn).search(q, limit=10000, offset=0)
            headers = ["ma_nhan_vien", "ho_ten", "don_vi", "loai_doi_tuong", "ket_qua", "can_cu", "ma_quy_tac"]
            rows = []
            for item in raw["ket_qua"]:
                x = _item_contract(conn, item)
                obj, st = x["doi_tuong"], x["trang_thai_tra_luong"]
                rows.append([
                    obj.get("ma_nhan_vien", ""),
                    obj.get("ho_ten", ""),
                    obj.get("don_vi") or obj.get("ten_don_vi", ""),
                    x["loai_doi_tuong"],
                    st.get("ket_qua"),
                    st.get("can_cu") or "",
                    st.get("ma_quy_tac") or ""
                ])
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in q)[:60] or "search"
            if format.lower() == "xlsx":
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Ket_Qua_Tra_Cuu"
                ws.append(headers)
                for r in rows:
                    ws.append(r)
                buf = io.BytesIO()
                wb.save(buf)
                buf.seek(0)
                return StreamingResponse(
                    buf,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="export_{safe}.xlsx"'}
                )
            text = io.StringIO()
            writer = csv.writer(text)
            writer.writerow(headers)
            writer.writerows(rows)
            return StreamingResponse(
                io.BytesIO(text.getvalue().encode("utf-8-sig")),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="export_{safe}.csv"'}
            )
        finally:
            conn.close()

    return app


app = create_app()
