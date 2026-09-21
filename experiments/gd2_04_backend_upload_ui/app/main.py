from __future__ import annotations
import csv
import io
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import DEFAULT_DB_PATH, ensure_database, get_connection
from .integration.search_rule_bridge import SearchRuleBridge
from .upload_service import commit_upload, preview_upload

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
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

    app = FastAPI(title="PayrollCheck GĐ2-04", version="2.4.1", lifespan=lifespan)
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    def conn_now():
        return get_connection(app.state.db_path)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return TEMPLATES.TemplateResponse(request, "index.html")

    @app.get("/health")
    def health():
        conn = conn_now()
        try:
            return {
                "status": "ok",
                "nhan_vien": conn.execute("SELECT COUNT(*) FROM nhan_vien").fetchone()[0],
                "business_rule": conn.execute("SELECT COUNT(*) FROM business_rule").fetchone()[0],
                "ngoai_le_ca_nhan": conn.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0],
                "don_vi_nguon": conn.execute("SELECT COUNT(*) FROM don_vi_nguon").fetchone()[0],
                "gd2_01_file_reader": True, "gd2_02_schema_mapping": True,
                "gd2_03_search_engine": True, "gd2_03_rule_engine": True,
                "gd2_04_upload_pipeline": True,
            }
        finally:
            conn.close()

    @app.get("/search")
    def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), page: Optional[int] = Query(None, ge=1)):
        conn = conn_now()
        try:
            actual_offset = (page - 1) * limit if page is not None else offset
            bridge = SearchRuleBridge(conn)
            raw = bridge.search(q, limit=limit, offset=actual_offset)
            items = [_item_contract(conn, x) for x in raw["ket_qua"]]
            total = raw["tong_ket_qua"]
            current_page = page if page is not None else actual_offset // limit + 1
            SEARCH_HISTORY.append({"query_id": f"QRY-{len(SEARCH_HISTORY)+1:04d}", "query": q, "object_name": items[0]["ten_hien_thi"] if items else "Không tìm thấy", "object_type": items[0]["loai_doi_tuong"] if items else "-", "result": items[0]["trang_thai_tra_luong"]["ket_qua"] if items else "CHUA_XAC_DINH", "rule": items[0]["trang_thai_tra_luong"].get("ma_quy_tac") if items else None})
            return {"query": q, "tong_ket_qua": total, "limit": limit, "offset": actual_offset, "page": current_page, "total_pages": max(1, (total + limit - 1)//limit), "ket_qua": items}
        finally:
            conn.close()

    @app.get("/employees/{employee_id}")
    def employee_detail(employee_id: int):
        conn = conn_now()
        try:
            row = conn.execute("SELECT * FROM nhan_vien WHERE id=?", (employee_id,)).fetchone()
            if not row: raise HTTPException(404, "Không tìm thấy nhân viên")
            status = SearchRuleBridge(conn).employee_status(row["ma_nhan_vien"])
            return {"doi_tuong": _row_dict(row), "trang_thai_tra_luong": status}
        finally: conn.close()

    @app.get("/payroll-status/employee/{employee_id}")
    def employee_payroll(employee_id: int):
        return employee_detail(employee_id)

    @app.get("/units/{unit_id}")
    def unit_detail(unit_id: int):
        conn = conn_now()
        try:
            row = conn.execute("SELECT * FROM don_vi WHERE id=?", (unit_id,)).fetchone()
            if not row: raise HTTPException(404, "Không tìm thấy đơn vị")
            status = SearchRuleBridge(conn).unit_status(row["ma_don_vi"])
            return {"doi_tuong": _row_dict(row), "trang_thai_tra_luong": status}
        finally: conn.close()

    @app.get("/payroll-status/unit/{unit_id}")
    def unit_payroll(unit_id: int):
        return unit_detail(unit_id)

    @app.post("/upload/preview")
    async def upload_preview(file: UploadFile = File(...), data_type: str = Query(...)):
        content = await file.read()
        if not content: raise HTTPException(400, "File rỗng")
        try: return preview_upload(content, file.filename or "upload.csv", data_type)
        except ValueError as exc: raise HTTPException(400, str(exc)) from exc

    @app.post("/upload/commit")
    async def upload_commit(file: UploadFile = File(...), data_type: str = Query(...), mode: str = Query("APPEND")):
        content = await file.read()
        if not content: raise HTTPException(400, "File rỗng")
        conn = conn_now()
        try:
            result = commit_upload(conn, content, file.filename or "upload.csv", data_type, mode)
            if not result.get("ok"): raise HTTPException(422, detail=result)
            return result
        except (ValueError, RuntimeError) as exc: raise HTTPException(400, str(exc)) from exc
        finally: conn.close()

    def _export(q: str, fmt: str):
        conn = conn_now()
        try:
            raw = SearchRuleBridge(conn).search(q, limit=100000, offset=0)
            headers = ["ma_nhan_vien","ho_ten","don_vi","loai_doi_tuong","ket_qua","can_cu","ma_quy_tac"]
            rows = []
            for item in raw["ket_qua"]:
                x = _item_contract(conn, item)
                obj, st = x["doi_tuong"], x["trang_thai_tra_luong"]
                rows.append([obj.get("ma_nhan_vien", ""), obj.get("ho_ten", ""), obj.get("don_vi") or obj.get("ten_don_vi", ""), x["loai_doi_tuong"], st.get("ket_qua"), st.get("can_cu") or "", st.get("ma_quy_tac") or ""])
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in q)[:60] or "search"
            if fmt.lower() == "xlsx":
                wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Ket_Qua_Tim_Kiem"; ws.append(headers)
                for r in rows: ws.append(r)
                buf = io.BytesIO(); wb.save(buf); buf.seek(0)
                return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="export_{safe}.xlsx"'})
            text = io.StringIO(); writer = csv.writer(text); writer.writerow(headers); writer.writerows(rows)
            return StreamingResponse(io.BytesIO(text.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="export_{safe}.csv"'})
        finally: conn.close()

    @app.get("/export/search")
    def export_search(q: str = Query(..., min_length=1), format: str = Query("csv")):
        return _export(q, format)

    @app.get("/export")
    def export_alias(q: str = Query(..., min_length=1), format: str = Query("csv")):
        return _export(q, format)

    @app.get("/api/employees")
    def api_employees(page: int = 1, limit: int = 20, search: Optional[str] = None):
        conn = conn_now()
        try:
            offset = (page-1)*limit
            if search:
                p = f"%{search}%"; where = "WHERE ma_nhan_vien LIKE ? OR ho_ten LIKE ? OR don_vi LIKE ?"; params=(p,p,p)
            else: where=""; params=()
            total = conn.execute(f"SELECT COUNT(*) FROM nhan_vien {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM nhan_vien {where} ORDER BY id LIMIT ? OFFSET ?", params+(limit,offset)).fetchall()
            bridge = SearchRuleBridge(conn)
            return {"total": total, "page": page, "limit": limit, "total_pages": max(1,(total+limit-1)//limit), "employees": [{**_row_dict(r), "trang_thai_tra_luong": bridge.employee_status(r["ma_nhan_vien"])} for r in rows]}
        finally: conn.close()

    @app.get("/api/units")
    def api_units():
        conn = conn_now()
        try:
            bridge = SearchRuleBridge(conn); rows = conn.execute("SELECT * FROM don_vi ORDER BY ten_don_vi_chuan").fetchall()
            return {"units": [{**_row_dict(r), "employee_count": conn.execute("SELECT COUNT(*) FROM nhan_vien WHERE ma_don_vi=?",(r["ma_don_vi"],)).fetchone()[0], "trang_thai_tra_luong": bridge.unit_status(r["ma_don_vi"])} for r in rows]}
        finally: conn.close()

    @app.get("/api/rules")
    def api_rules():
        conn=conn_now()
        try: return {"rules": [_row_dict(r) for r in conn.execute("SELECT * FROM business_rule ORDER BY muc_uu_tien DESC,id DESC").fetchall()]}
        finally: conn.close()

    @app.get("/api/exceptions")
    def api_exceptions():
        conn=conn_now()
        try: return {"exceptions": [_row_dict(r) for r in conn.execute("SELECT * FROM ngoai_le_ca_nhan ORDER BY muc_uu_tien DESC,id DESC").fetchall()]}
        finally: conn.close()

    @app.get("/api/history")
    def api_history(): return {"history": list(reversed(SEARCH_HISTORY[-30:]))}

    @app.get("/api/dashboard/stats")
    def dashboard_stats():
        conn=conn_now()
        try:
            total_nv=conn.execute("SELECT COUNT(*) FROM nhan_vien").fetchone()[0]
            bridge=SearchRuleBridge(conn); yes=no=undef=0
            for r in conn.execute("SELECT ma_nhan_vien FROM nhan_vien LIMIT 100").fetchall():
                k=bridge.employee_status(r["ma_nhan_vien"])["ket_qua"]
                yes += k=="YES"; no += k=="NO"; undef += k=="CHUA_XAC_DINH"
            return {"total_employees":total_nv,"total_units":conn.execute("SELECT COUNT(*) FROM don_vi").fetchone()[0],"total_rules":conn.execute("SELECT COUNT(*) FROM business_rule").fetchone()[0],"total_exceptions":conn.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0],"count_yes":yes,"count_no":no,"count_unidentified":undef}
        finally: conn.close()

    @app.get("/api/system")
    def system_info():
        import socket
        return {"server_status":"ONLINE","database_status":"CONNECTED","search_engine":"GD2-03","rule_engine":"GD2-03","ocr_engine":"GD2-01","version":"2.4.1","host_name":socket.gethostname(),"port":8000}

    return app

app = create_app()
