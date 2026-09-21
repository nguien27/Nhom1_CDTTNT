from __future__ import annotations

import csv
import io
import json
import os
import socket
from datetime import datetime
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import AuthService, SESSION_COOKIE_NAME
from .database import Database, get_database
from .integration.engine_bridge import (
    ConnectionRepositoryAdapter,
    RuleEngine,
    SearchEngine,
)
from .integration.upstream_bridge import (
    CommitService,
    InputAnalysisError,
    MappingService,
    SCHEMA_FIELDS,
    ValidationService,
    analyze_input,
)
from experiments.gd2_04_backend_upload_ui.app.normalization import (
    chuan_hoa_ho_ten,
    chuan_hoa_ho_ten_chuan,
    chuan_hoa_ket_qua,
    chuan_hoa_msnv,
    chuan_hoa_ten_don_vi,
    chuan_hoa_tim_kiem,
    chuan_hoa_unicode,
)


DATA_TYPE = "NHAN_VIEN_KHONG_KET_QUA"

SUPPORTED_DATA_TYPES = {
    "NHAN_VIEN_KHONG_KET_QUA",
    "NHAN_VIEN_CO_KET_QUA",
    "DON_VI",
    "BUSINESS_RULE",
}

# Lịch sử tra cứu trong phiên chạy hiện tại.
# Restart server thì lịch sử này được reset.
SEARCH_HISTORY: List[Dict[str, Any]] = []

# GĐ4 Final Integration UI
PROJECT_ROOT = Path(__file__).resolve().parents[3]
GD3_03_UI_ROOT = PROJECT_ROOT / "experiments" / "gd3_03_input_mapping_ui"
UI_STATIC_DIR = GD3_03_UI_ROOT / "static"
UI_TEMPLATE_DIR = GD3_03_UI_ROOT / "templates"
UI_TEMPLATES = Jinja2Templates(directory=str(UI_TEMPLATE_DIR))


def _row_dict(row: Any) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()} if row is not None else {}


def _error(status_code: int, message: str, **extra):
    payload = {"status": "error", "message": message}
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _validate_iso_date(value: Any, field_label: str) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} phải có định dạng YYYY-MM-DD.",
        ) from exc
    return cleaned


def _validate_exception_dates(start: str | None, end: str | None) -> None:
    if start and end and end < start:
        raise HTTPException(
            status_code=400,
            detail="Ngày hết hiệu lực không được trước ngày hiệu lực.",
        )


def _extract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = payload.get("rows") or payload.get("records") or payload.get("data") or []
    return rows if isinstance(rows, list) else []


def _extract_mapping(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    mapping = payload.get("mapping_items") or payload.get("mapping") or []
    return mapping if isinstance(mapping, list) else []


def _extract_data_type(payload: Dict[str, Any]) -> str:
    data_type = str(
        payload.get("data_type")
        or DATA_TYPE
    ).strip().upper()

    if data_type not in SUPPORTED_DATA_TYPES:
        raise ValueError(
            f"Loại dữ liệu không hỗ trợ: {data_type}"
        )

    return data_type


def _target_source_map(mapping_items: List[Dict[str, Any]]) -> Dict[str, str]:
    """Đổi mapping UI thành target -> source để kiểm tra tham chiếu trước Commit."""
    result: Dict[str, str] = {}
    for item in mapping_items:
        target = str(item.get("target_field") or "").strip()
        source = str(item.get("source_column") or "").strip()
        if target and source and target not in {"IGNORE", "OTHER"}:
            result[target] = source
    return result


def _reference_validation_errors(
    db: Database,
    rows: List[Dict[str, Any]],
    mapping_items: List[Dict[str, Any]],
    data_type: str,
) -> List[str]:
    """Kiểm tra các tham chiếu DB mà ValidationService thuần schema không biết."""
    target_map = _target_source_map(mapping_items)
    errors: List[str] = []
    conn = db.get_connection()

    if data_type == "BUSINESS_RULE":
        source = target_map.get("TEN_DON_VI")
        if source:
            with db.lock:
                known = {
                    row[0]
                    for row in conn.execute(
                        "SELECT ten_don_vi_chuan FROM don_vi"
                    ).fetchall()
                }
            for index, row in enumerate(rows, start=1):
                unit_name = chuan_hoa_ten_don_vi(row.get(source))
                if unit_name and chuan_hoa_tim_kiem(unit_name) not in known:
                    errors.append(
                        f"Dòng {index}: đơn vị '{unit_name}' chưa tồn tại. "
                        "Hãy nhập đơn vị trước khi nạp Business Rule."
                    )

    elif data_type == "NHAN_VIEN_CO_KET_QUA":
        source = target_map.get("MA_NHAN_VIEN")
        if source:
            with db.lock:
                known = {
                    str(row[0] or "").upper()
                    for row in conn.execute(
                        "SELECT ma_nhan_vien FROM nhan_vien"
                    ).fetchall()
                }
            for index, row in enumerate(rows, start=1):
                employee_code = chuan_hoa_msnv(row.get(source))
                if employee_code and employee_code.upper() not in known:
                    errors.append(
                        f"Dòng {index}: mã nhân viên '{employee_code}' chưa tồn tại. "
                        "Hãy nhập hồ sơ nhân viên trước khi nạp ngoại lệ."
                    )

    return errors


def _mapping_summary(
    mapping_service: MappingService,
    mapping_items: List[Dict[str, Any]],
    data_type: str = DATA_TYPE,
) -> Dict[str, Any]:
    return {
        "duplicates":
            mapping_service.find_duplicate_mappings(
                mapping_items
            ),

        "missing_fields":
            mapping_service.find_missing_required(
                mapping_items,
                data_type,
            ),

        "pending_confirmation":
            mapping_service.find_pending_confirmation(
                mapping_items
            ),
    }


def _analyse_and_map(
    mapping_service: MappingService,
    *,
    content: bytes | None,
    filename: str | None,
    raw_text: str | None,
    input_method: str,
    data_type: str = DATA_TYPE,
) -> Dict[str, Any]:
    analysed = analyze_input(
        content=content,
        filename=filename,
        raw_text=raw_text,
        input_method=input_method,
        data_type=data_type,
    )

    if analysed.get("structured_direct"):
        mapping = mapping_service.generate_mapping(
            headers=analysed["headers"],
            sample_rows=analysed["rows"],
            data_type=data_type,
        )
    else:
        mapping = mapping_service.generate_from_pipeline(
            pipeline_payload=analysed["pipeline_payload"],
            headers=analysed["headers"],
            sample_rows=analysed["rows"],
            data_type=data_type,
        )

    upstream_validation = analysed.get(
        "upstream_validation"
    )

    if data_type != "NHAN_VIEN_KHONG_KET_QUA":
        # Upstream validator của GĐ3-02 được thiết kế cho employee schema
        # mặc định. Với các schema mở rộng, ValidationService sau mapping
        # mới là nguồn kiểm tra canonical.
        upstream_validation = None

    return {
        "status": "ok",
        "data_type": data_type,
        "headers": analysed["headers"],
        "rows": analysed["rows"],
        "preview_rows": analysed["preview_rows"],
        "metadata": analysed["metadata"],
        "mapping_items": mapping["mapping_items"],
        "schema_options": mapping["schema_options"],
        "duplicates": mapping["duplicates"],
        "missing_fields": mapping["missing_fields"],
        "pending_confirmation":
            mapping["pending_confirmation"],
        "requires_confirmation": bool(
            mapping["pending_confirmation"]
        ),
        "upstream_validation":
            upstream_validation,
        "upstream_validation_note": (
            "Schema mở rộng được ValidationService "
            "kiểm tra sau bước mapping."
            if data_type != "NHAN_VIEN_KHONG_KET_QUA"
            else None
        ),
        "source_pipeline":
            "GD3-01 -> GD3-02 -> GD3-03 -> GD3-04",
    }


def create_app(
    db_path: str | Path | None = None,
    auth_enabled: bool | None = None,
) -> FastAPI:
    db = get_database(db_path)
    repo = ConnectionRepositoryAdapter(db.get_connection(), db.lock)

    app = FastAPI(
        title="PayrollCheck - Hệ thống Tra cứu Chi trả Lương",
        version="4.0.0",
    )

    # GĐ4: GĐ3-04 là server duy nhất và serve UI của GĐ3-03.
    if UI_STATIC_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(UI_STATIC_DIR)),
            name="static",
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def gd4_ui(request: Request):
        return UI_TEMPLATES.TemplateResponse(request, "index.html")
    app.state.db = db
    app.state.repo = repo
    app.state.search_engine = SearchEngine(repo)
    app.state.rule_engine = RuleEngine(repo)
    app.state.mapping_service = None
    app.state.validation_service = None

    # Runtime production luôn bật auth. :memory: mặc định giữ compatibility
    # cho bộ regression GĐ3-04 cũ; test auth mới bật auth_enabled=True.
    app.state.auth_enabled = (db_path != ":memory:") if auth_enabled is None else bool(auth_enabled)
    app.state.auth_service = AuthService(db.get_connection(), db.lock)
    app.state.admin_account = app.state.auth_service.ensure_admin_from_env()

    def _legacy_test_admin() -> Dict[str, Any]:
        return {
            "id": 0,
            "username": "TEST_ADMIN",
            "role": "ADMIN",
            "ma_nhan_vien": None,
            "email": None,
            "must_change_password": False,
            "is_active": True,
        }

    def current_user(request: Request) -> Dict[str, Any]:
        if not app.state.auth_enabled:
            return _legacy_test_admin()
        token = request.cookies.get(SESSION_COOKIE_NAME)
        user = app.state.auth_service.get_user_by_session(token)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AUTH_REQUIRED",
                    "message": "Bạn cần đăng nhập để sử dụng chức năng này.",
                },
            )
        return user

    def require_ready_user(
        user: Dict[str, Any] = Depends(current_user),
    ) -> Dict[str, Any]:
        if user.get("must_change_password"):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PASSWORD_CHANGE_REQUIRED",
                    "message": "Bạn phải đổi mật khẩu lần đầu trước khi sử dụng hệ thống.",
                },
            )
        return user

    def require_admin(
        user: Dict[str, Any] = Depends(require_ready_user),
    ) -> Dict[str, Any]:
        if user.get("role") != "ADMIN":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ADMIN_REQUIRED",
                    "message": "Chức năng này chỉ dành cho ADMIN.",
                },
            )
        return user

    @app.post("/api/auth/login")
    def auth_login(response: Response, payload: Dict[str, Any] = Body(...)):
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="Thiếu username hoặc password.")
        user = app.state.auth_service.authenticate(username, password)
        if user is None:
            raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
        token = app.state.auth_service.create_session(user["id"])
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=os.getenv("PAYROLLCHECK_COOKIE_SECURE", "0").strip() in {"1", "true", "TRUE"},
            max_age=int(os.getenv("PAYROLLCHECK_SESSION_HOURS", "12")) * 3600,
            path="/",
        )
        return {"status": "ok", "user": user}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response):
        app.state.auth_service.revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return {"status": "ok"}

    @app.get("/api/auth/me")
    def auth_me(user: Dict[str, Any] = Depends(current_user)):
        return {"status": "ok", "user": user}

    @app.post("/api/auth/change-password")
    def auth_change_password(
        payload: Dict[str, Any] = Body(...),
        user: Dict[str, Any] = Depends(current_user),
    ):
        try:
            updated = app.state.auth_service.change_password(
                user["id"],
                str(payload.get("current_password") or ""),
                str(payload.get("new_password") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok", "user": updated}

    def mapping_service() -> MappingService:
        if app.state.mapping_service is None:
            app.state.mapping_service = MappingService()
        return app.state.mapping_service

    def validation_service() -> ValidationService:
        if app.state.validation_service is None:
            app.state.validation_service = ValidationService()
        return app.state.validation_service

    @app.get("/health")
    def health():
        conn = db.get_connection()
        with db.lock:
            counts = {
                "nhan_vien": conn.execute("SELECT COUNT(*) FROM nhan_vien").fetchone()[0],
                "don_vi": conn.execute("SELECT COUNT(*) FROM don_vi").fetchone()[0],
                "business_rule": conn.execute("SELECT COUNT(*) FROM business_rule").fetchone()[0],
                "ngoai_le_ca_nhan": conn.execute("SELECT COUNT(*) FROM ngoai_le_ca_nhan").fetchone()[0],
            }
        return {
            "status": "ok",
            "service": "payrollcheck",
            "version": "4.0.0",
            "bind_default": "0.0.0.0:8000",
            "modules": {
                "gd3_01_universal_input": True,
                "gd3_02_information_mapping": True,
                "gd3_03_input_mapping_ui": True,
                "gd2_03_search_rule_engine": True,
            },
            **counts,
        }

    # =========================================================
    # GĐ4-02C - API danh sách nhân viên cho giao diện quản trị
    # =========================================================

    @app.get("/api/employees", dependencies=[Depends(require_admin)])
    def api_employees(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        search: Optional[str] = Query(None),
    ):
        offset = (page - 1) * limit

        conn = db.get_connection()

        with db.lock:
            if search and search.strip():
                pattern = f"%{search.strip()}%"

                total = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM nhan_vien
                    WHERE ma_nhan_vien LIKE ?
                       OR ho_ten LIKE ?
                       OR don_vi LIKE ?
                    """,
                    (
                        pattern,
                        pattern,
                        pattern,
                    ),
                ).fetchone()[0]

                rows = conn.execute(
                    """
                    SELECT *
                    FROM nhan_vien
                    WHERE ma_nhan_vien LIKE ?
                       OR ho_ten LIKE ?
                       OR don_vi LIKE ?
                    ORDER BY id
                    LIMIT ? OFFSET ?
                    """,
                    (
                        pattern,
                        pattern,
                        pattern,
                        limit,
                        offset,
                    ),
                ).fetchall()

            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM nhan_vien"
                ).fetchone()[0]

                rows = conn.execute(
                    """
                    SELECT *
                    FROM nhan_vien
                    ORDER BY id
                    LIMIT ? OFFSET ?
                    """,
                    (
                        limit,
                        offset,
                    ),
                ).fetchall()

        employees = []

        for row in rows:
            item = _row_dict(row)

            item["trang_thai_tra_luong"] = (
                app.state.rule_engine
                .evaluate_employee_salary_rule(
                    item["ma_nhan_vien"]
                )
            )

            employees.append(item)

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(
                1,
                (total + limit - 1) // limit,
            ),
            "employees": employees,
        }

    @app.get("/api/employees/{ma_nhan_vien}", dependencies=[Depends(require_admin)])
    def api_employee_detail(ma_nhan_vien: str):
        ma = chuan_hoa_msnv(ma_nhan_vien)
        conn = db.get_connection()
        with db.lock:
            row = conn.execute(
                "SELECT * FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()
            account = conn.execute(
                "SELECT id, username, role, email, must_change_password, is_active "
                "FROM users WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
        item = _row_dict(row)
        item["is_active"] = bool(item.get("is_active", 1))
        return {
            "status": "ok",
            "employee": item,
            "account": _row_dict(account) if account is not None else None,
        }

    @app.patch("/api/employees/{ma_nhan_vien}", dependencies=[Depends(require_admin)])
    def api_update_employee(ma_nhan_vien: str, payload: Dict[str, Any] = Body(...)):
        ma = chuan_hoa_msnv(ma_nhan_vien)
        ho_ten = chuan_hoa_ho_ten(payload.get("ho_ten"))
        ten_don_vi = chuan_hoa_ten_don_vi(payload.get("ten_don_vi") or payload.get("don_vi"))
        chuc_vu = _optional_text(payload.get("chuc_vu"))
        email = _optional_text(payload.get("email"))

        if not ho_ten:
            raise HTTPException(status_code=400, detail="Họ tên không được để trống.")
        if not ten_don_vi:
            raise HTTPException(status_code=400, detail="Tên đơn vị không được để trống.")
        if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
            raise HTTPException(status_code=400, detail="Email không hợp lệ.")

        conn = db.get_connection()
        with db.lock:
            employee = conn.execute(
                "SELECT id, is_active FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()
            if employee is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

            unit = conn.execute(
                "SELECT ma_don_vi, ten_don_vi FROM don_vi "
                "WHERE lower(trim(ten_don_vi))=lower(trim(?)) LIMIT 1",
                (ten_don_vi,),
            ).fetchone()
            if unit is None:
                raise HTTPException(
                    status_code=400,
                    detail="Đơn vị chưa tồn tại trong danh mục. Hãy chọn một đơn vị đã có.",
                )

            conn.execute(
                """
                UPDATE nhan_vien
                SET ho_ten=?, ho_ten_chuan=?, ma_don_vi=?, ten_don_vi=?, don_vi=?,
                    chuc_vu=?, email=?, updated_at=CURRENT_TIMESTAMP
                WHERE upper(ma_nhan_vien)=upper(?)
                """,
                (
                    ho_ten,
                    chuan_hoa_ho_ten_chuan(ho_ten),
                    unit["ma_don_vi"],
                    unit["ten_don_vi"],
                    unit["ten_don_vi"],
                    chuc_vu,
                    email,
                    ma,
                ),
            )
            # Chỉ đồng bộ email mô tả. Không thay đổi mật khẩu hiện tại.
            conn.execute(
                "UPDATE users SET email=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE upper(ma_nhan_vien)=upper(?)",
                (email, ma),
            )
            conn.commit()

        account_result = None
        if bool(employee["is_active"]):
            account_result = app.state.auth_service.ensure_employee_accounts([ma])
        return {
            "status": "ok",
            "message": "Đã cập nhật hồ sơ nhân viên.",
            "account_sync": account_result,
        }

    @app.patch("/api/employees/{ma_nhan_vien}/status", dependencies=[Depends(require_admin)])
    def api_set_employee_status(ma_nhan_vien: str, payload: Dict[str, Any] = Body(...)):
        ma = chuan_hoa_msnv(ma_nhan_vien)
        if "is_active" not in payload or not isinstance(payload.get("is_active"), bool):
            raise HTTPException(status_code=400, detail="Thiếu trạng thái is_active hợp lệ.")
        is_active = bool(payload["is_active"])
        conn = db.get_connection()

        with db.lock:
            row = conn.execute(
                "SELECT id FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

            conn.execute(
                "UPDATE nhan_vien SET is_active=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE upper(ma_nhan_vien)=upper(?)",
                (1 if is_active else 0, ma),
            )
            conn.execute(
                "UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE upper(ma_nhan_vien)=upper(?)",
                (1 if is_active else 0, ma),
            )
            if not is_active:
                conn.execute(
                    """
                    UPDATE auth_sessions
                    SET revoked_at=CURRENT_TIMESTAMP
                    WHERE revoked_at IS NULL
                      AND user_id IN (
                          SELECT id FROM users WHERE upper(ma_nhan_vien)=upper(?)
                      )
                    """,
                    (ma,),
                )
            conn.commit()

        account_result = None
        if is_active:
            # Nếu trước đây nhân viên chưa có account nhưng hiện đã có email,
            # kích hoạt hồ sơ cũng tạo USER theo đúng quy tắc hiện hành.
            account_result = app.state.auth_service.ensure_employee_accounts([ma])

        return {
            "status": "ok",
            "is_active": is_active,
            "message": "Đã kích hoạt lại nhân viên." if is_active else "Đã ngừng hoạt động nhân viên.",
            "account_sync": account_result,
        }

    @app.delete("/api/employees/{ma_nhan_vien}", dependencies=[Depends(require_admin)])
    def api_delete_employee(ma_nhan_vien: str):
        ma = chuan_hoa_msnv(ma_nhan_vien)
        conn = db.get_connection()
        with db.lock:
            row = conn.execute(
                "SELECT id, ho_ten FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

            account_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM users WHERE upper(ma_nhan_vien)=upper(?)",
                    (ma,),
                ).fetchall()
            ]
            deleted_exceptions = conn.execute(
                "SELECT COUNT(*) FROM ngoai_le_ca_nhan WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            ).fetchone()[0]

            for user_id in account_ids:
                conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            conn.execute(
                "DELETE FROM users WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            )
            conn.execute(
                "DELETE FROM ngoai_le_ca_nhan WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            )
            conn.execute(
                "DELETE FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (ma,),
            )
            conn.commit()

        return {
            "status": "ok",
            "message": f"Đã xóa vĩnh viễn nhân viên {ma}.",
            "deleted_accounts": len(account_ids),
            "deleted_exceptions": int(deleted_exceptions),
        }

    # =========================================================
    # GĐ4-02C - API danh sách đơn vị cho giao diện quản trị
    # =========================================================

    @app.get("/api/units", dependencies=[Depends(require_admin)])
    def api_units():
        conn = db.get_connection()

        with db.lock:
            rows = conn.execute(
                """
                SELECT *
                FROM don_vi
                ORDER BY ten_don_vi_chuan, id
                """
            ).fetchall()

        units = []

        for row in rows:
            item = _row_dict(row)

            ma_don_vi = item.get("ma_don_vi")

            with db.lock:
                employee_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM nhan_vien
                    WHERE ma_don_vi = ?
                    """,
                    (ma_don_vi,),
                ).fetchone()[0]

            business_status = (
                app.state.rule_engine
                .evaluate_unit_salary_rule(
                    ma_don_vi
                )
            )

            metadata = {}
            try:
                metadata = json.loads(
                    item.get("thong_tin_mo_rong")
                    or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata = {}

            units.append({
                **item,

                # Giữ field tương thích với UI GĐ3-03 và bảo toàn
                # metadata nguồn khi đơn vị được import ở GĐ4.
                "ma_don_vi_nguon":
                    metadata.get("ma_don_vi_nguon")
                    or ma_don_vi,
                "don_vi_cha":
                    metadata.get("don_vi_cha"),

                "employee_count": employee_count,

                "trang_thai_tra_luong":
                    business_status,
            })

        return {
            "total": len(units),
            "units": units,
        }

    # =========================================================
    # GĐ4-02C - Thống kê Dashboard
    # =========================================================

    @app.get("/api/dashboard/stats", dependencies=[Depends(require_admin)])
    def api_dashboard_stats():
        conn = db.get_connection()

        # Chỉ lấy dữ liệu DB trong lock.
        with db.lock:
            total_employees = conn.execute(
                "SELECT COUNT(*) FROM nhan_vien"
            ).fetchone()[0]

            total_units = conn.execute(
                "SELECT COUNT(*) FROM don_vi"
            ).fetchone()[0]

            total_rules = conn.execute(
                "SELECT COUNT(*) FROM business_rule"
            ).fetchone()[0]

            total_exceptions = conn.execute(
                "SELECT COUNT(*) FROM ngoai_le_ca_nhan"
            ).fetchone()[0]

            employee_rows = conn.execute(
                """
                SELECT ma_nhan_vien
                FROM nhan_vien
                ORDER BY id
                """
            ).fetchall()

        count_yes = 0
        count_no = 0
        count_unidentified = 0

        # RuleEngine canonical GĐ2-03 tự quyết định trạng thái.
        for row in employee_rows:
            result = (
                app.state.rule_engine
                .evaluate_employee_salary_rule(
                    row["ma_nhan_vien"]
                )
            )

            status = result.get(
                "ket_qua",
                "CHUA_XAC_DINH",
            )

            if status == "YES":
                count_yes += 1

            elif status == "NO":
                count_no += 1

            else:
                count_unidentified += 1

        return {
            "total_employees": total_employees,
            "total_units": total_units,

            "total_rules": total_rules,
            "total_exceptions": total_exceptions,

            "count_yes": count_yes,
            "count_no": count_no,

            "count_unidentified":
                count_unidentified,
        }

    # =========================================================
    # GĐ4-02C - API danh sách Business Rule
    # =========================================================

    def _rule_display_status(rule: Dict[str, Any]) -> str:
        if int(rule.get("dang_ap_dung") or 0) != 1:
            return "NGUNG_AP_DUNG"
        today = datetime.now().date().isoformat()
        start_date = _clean_text(rule.get("ngay_hieu_luc"))
        end_date = _clean_text(rule.get("ngay_het_hieu_luc"))
        if start_date and start_date > today:
            return "CHUA_HIEU_LUC"
        if end_date and end_date < today:
            return "HET_HIEU_LUC"
        return "DANG_AP_DUNG"

    @app.get("/api/rules", dependencies=[Depends(require_admin)])
    def api_rules():
        conn = db.get_connection()
        with db.lock:
            rows = conn.execute(
                "SELECT * FROM business_rule ORDER BY id DESC"
            ).fetchall()
        rules = []
        for row in rows:
            item = _row_dict(row)
            item["trang_thai"] = _rule_display_status(item)
            rules.append(item)
        return {"total": len(rules), "rules": rules}

    def _rule_values(payload: Dict[str, Any], *, current_code: str | None = None) -> Dict[str, Any]:
        ten_quy_tac = chuan_hoa_unicode(payload.get("ten_quy_tac"))
        ten_don_vi = chuan_hoa_ten_don_vi(payload.get("ten_don_vi"))
        ket_qua = chuan_hoa_ket_qua(payload.get("ket_qua"))
        can_cu = chuan_hoa_unicode(payload.get("can_cu"))
        ma_quy_tac = _clean_text(payload.get("ma_quy_tac")) or current_code
        if not ten_quy_tac:
            raise HTTPException(status_code=400, detail="Tên quy tắc không được để trống.")
        if not ten_don_vi:
            raise HTTPException(status_code=400, detail="Tên đơn vị áp dụng không được để trống.")
        if ket_qua not in {"YES", "NO"}:
            raise HTTPException(status_code=400, detail="Kết quả chỉ được là YES hoặc NO.")
        if not can_cu:
            raise HTTPException(status_code=400, detail="Căn cứ pháp lý / nghiệp vụ không được để trống.")

        conn = db.get_connection()
        with db.lock:
            unit = conn.execute(
                "SELECT ma_don_vi, ten_don_vi FROM don_vi WHERE ten_don_vi_chuan=?",
                (chuan_hoa_tim_kiem(ten_don_vi),),
            ).fetchone()
        if unit is None:
            raise HTTPException(
                status_code=400,
                detail="Đơn vị áp dụng chưa tồn tại. Hãy nhập đơn vị trước khi tạo quy tắc.",
            )
        return {
            "ma_quy_tac": ma_quy_tac,
            "ten_quy_tac": ten_quy_tac,
            "ma_don_vi": unit["ma_don_vi"],
            "ten_don_vi": unit["ten_don_vi"],
            "ket_qua": ket_qua,
            "can_cu": can_cu,
        }

    @app.post("/api/rules", dependencies=[Depends(require_admin)])
    def api_create_rule(payload: Dict[str, Any] = Body(...)):
        values = _rule_values(payload)
        ma_quy_tac = values["ma_quy_tac"] or (
            f"BR_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6].upper()}"
        )
        conn = db.get_connection()
        with db.lock:
            exists = conn.execute(
                "SELECT id FROM business_rule WHERE ma_quy_tac=?",
                (ma_quy_tac,),
            ).fetchone()
            if exists:
                raise HTTPException(status_code=409, detail="Mã quy tắc đã tồn tại.")
            cur = conn.execute(
                """
                INSERT INTO business_rule(
                    ma_quy_tac, ten_quy_tac, pham_vi, ma_don_vi, ten_don_vi,
                    loai_don_vi, ket_qua, can_cu, muc_uu_tien,
                    ngay_hieu_luc, ngay_het_hieu_luc, dang_ap_dung, la_mock
                ) VALUES(?,?,'DON_VI',?,?,NULL,?,?,0,NULL,NULL,1,0)
                """,
                (
                    ma_quy_tac, values["ten_quy_tac"], values["ma_don_vi"],
                    values["ten_don_vi"], values["ket_qua"], values["can_cu"],
                ),
            )
            conn.commit()
            rule_id = cur.lastrowid
        return {"status": "ok", "id": rule_id, "ma_quy_tac": ma_quy_tac, "message": "Đã thêm quy tắc."}

    @app.put("/api/rules/{rule_id}", dependencies=[Depends(require_admin)])
    def api_update_rule(rule_id: int, payload: Dict[str, Any] = Body(...)):
        conn = db.get_connection()
        with db.lock:
            current = conn.execute(
                "SELECT ma_quy_tac FROM business_rule WHERE id=?",
                (rule_id,),
            ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc.")
        values = _rule_values(payload, current_code=current["ma_quy_tac"])
        with db.lock:
            conn.execute(
                """
                UPDATE business_rule
                SET ten_quy_tac=?, pham_vi='DON_VI', ma_don_vi=?, ten_don_vi=?,
                    loai_don_vi=NULL, ket_qua=?, can_cu=?, muc_uu_tien=0,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    values["ten_quy_tac"], values["ma_don_vi"], values["ten_don_vi"],
                    values["ket_qua"], values["can_cu"], rule_id,
                ),
            )
            conn.commit()
        return {"status": "ok", "message": "Đã cập nhật quy tắc."}

    @app.patch("/api/rules/{rule_id}/status", dependencies=[Depends(require_admin)])
    def api_set_rule_status(rule_id: int, payload: Dict[str, Any] = Body(...)):
        if "is_active" not in payload or not isinstance(payload.get("is_active"), bool):
            raise HTTPException(status_code=400, detail="Thiếu trạng thái is_active hợp lệ.")
        is_active = bool(payload["is_active"])
        conn = db.get_connection()
        with db.lock:
            cur = conn.execute(
                "UPDATE business_rule SET dang_ap_dung=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (1 if is_active else 0, rule_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc.")
            conn.commit()
        return {
            "status": "ok",
            "is_active": is_active,
            "message": "Đã kích hoạt quy tắc." if is_active else "Đã ngừng áp dụng quy tắc.",
        }

    @app.delete("/api/rules/{rule_id}", dependencies=[Depends(require_admin)])
    def api_delete_rule(rule_id: int):
        conn = db.get_connection()
        with db.lock:
            cur = conn.execute("DELETE FROM business_rule WHERE id=?", (rule_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc.")
            conn.commit()
        return {"status": "ok", "message": "Đã xóa quy tắc."}

    # =========================================================
    # API quản lý Ngoại lệ cá nhân
    # =========================================================

    @app.get("/api/exceptions", dependencies=[Depends(require_admin)])
    def api_exceptions():
        conn = db.get_connection()

        with db.lock:
            rows = conn.execute(
                """
                SELECT
                    ex.*,
                    nv.ho_ten,
                    nv.don_vi
                FROM ngoai_le_ca_nhan ex
                LEFT JOIN nhan_vien nv
                    ON UPPER(ex.ma_nhan_vien)
                     = UPPER(nv.ma_nhan_vien)
                ORDER BY
                    ex.dang_ap_dung DESC,
                    ex.muc_uu_tien DESC,
                    ex.id DESC
                """
            ).fetchall()

        return {
            "total": len(rows),
            "exceptions": [_row_dict(row) for row in rows],
        }

    def _exception_values(payload: Dict[str, Any]) -> Dict[str, Any]:
        ma = chuan_hoa_msnv(payload.get("ma_nhan_vien"))
        ket_qua = _clean_text(payload.get("ket_qua")).upper()
        can_cu = _clean_text(payload.get("can_cu"))
        ghi_chu = _optional_text(payload.get("ghi_chu"))
        if not ma:
            raise HTTPException(status_code=400, detail="Mã nhân viên không được để trống.")
        if ket_qua not in {"YES", "NO"}:
            raise HTTPException(status_code=400, detail="Kết quả ngoại lệ chỉ được là YES hoặc NO.")
        if not can_cu:
            raise HTTPException(status_code=400, detail="Căn cứ ngoại lệ không được để trống.")
        try:
            muc_uu_tien = int(payload.get("muc_uu_tien", 100))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Mức ưu tiên phải là số nguyên.") from exc
        if muc_uu_tien < 0 or muc_uu_tien > 100000:
            raise HTTPException(status_code=400, detail="Mức ưu tiên không hợp lệ.")
        ngay_hieu_luc = _validate_iso_date(payload.get("ngay_hieu_luc"), "Ngày hiệu lực")
        ngay_het_hieu_luc = _validate_iso_date(payload.get("ngay_het_hieu_luc"), "Ngày hết hiệu lực")
        _validate_exception_dates(ngay_hieu_luc, ngay_het_hieu_luc)
        return {
            "ma_nhan_vien": ma,
            "ket_qua": ket_qua,
            "can_cu": can_cu,
            "muc_uu_tien": muc_uu_tien,
            "ngay_hieu_luc": ngay_hieu_luc,
            "ngay_het_hieu_luc": ngay_het_hieu_luc,
            "ghi_chu": ghi_chu,
        }

    @app.post("/api/exceptions", dependencies=[Depends(require_admin)])
    def api_create_exception(payload: Dict[str, Any] = Body(...)):
        values = _exception_values(payload)
        conn = db.get_connection()
        with db.lock:
            employee = conn.execute(
                "SELECT ma_nhan_vien FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (values["ma_nhan_vien"],),
            ).fetchone()
            if employee is None:
                raise HTTPException(status_code=400, detail="Mã nhân viên chưa tồn tại trong hệ thống.")

            ma_quy_tac = (
                f"EX_MANUAL_{values['ma_nhan_vien']}_"
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6].upper()}"
            )
            cur = conn.execute(
                """
                INSERT INTO ngoai_le_ca_nhan(
                    ma_quy_tac, ma_nhan_vien, ket_qua, can_cu, muc_uu_tien,
                    ngay_hieu_luc, ngay_het_hieu_luc, dang_ap_dung, la_mock, ghi_chu
                ) VALUES(?,?,?,?,?,?,?,1,0,?)
                """,
                (
                    ma_quy_tac, values["ma_nhan_vien"], values["ket_qua"],
                    values["can_cu"], values["muc_uu_tien"], values["ngay_hieu_luc"],
                    values["ngay_het_hieu_luc"], values["ghi_chu"],
                ),
            )
            conn.commit()
            exception_id = cur.lastrowid
        return {
            "status": "ok",
            "id": exception_id,
            "ma_quy_tac": ma_quy_tac,
            "message": "Đã thêm ngoại lệ cá nhân.",
        }

    @app.put("/api/exceptions/{exception_id}", dependencies=[Depends(require_admin)])
    def api_update_exception(exception_id: int, payload: Dict[str, Any] = Body(...)):
        values = _exception_values(payload)
        conn = db.get_connection()
        with db.lock:
            current = conn.execute(
                "SELECT id FROM ngoai_le_ca_nhan WHERE id=?",
                (exception_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy ngoại lệ.")
            employee = conn.execute(
                "SELECT ma_nhan_vien FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                (values["ma_nhan_vien"],),
            ).fetchone()
            if employee is None:
                raise HTTPException(status_code=400, detail="Mã nhân viên chưa tồn tại trong hệ thống.")
            conn.execute(
                """
                UPDATE ngoai_le_ca_nhan
                SET ma_nhan_vien=?, ket_qua=?, can_cu=?, muc_uu_tien=?,
                    ngay_hieu_luc=?, ngay_het_hieu_luc=?, ghi_chu=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    values["ma_nhan_vien"], values["ket_qua"], values["can_cu"],
                    values["muc_uu_tien"], values["ngay_hieu_luc"],
                    values["ngay_het_hieu_luc"], values["ghi_chu"], exception_id,
                ),
            )
            conn.commit()
        return {"status": "ok", "message": "Đã cập nhật ngoại lệ cá nhân."}

    @app.patch("/api/exceptions/{exception_id}/status", dependencies=[Depends(require_admin)])
    def api_set_exception_status(exception_id: int, payload: Dict[str, Any] = Body(...)):
        if "is_active" not in payload or not isinstance(payload.get("is_active"), bool):
            raise HTTPException(status_code=400, detail="Thiếu trạng thái is_active hợp lệ.")
        is_active = bool(payload["is_active"])
        conn = db.get_connection()
        with db.lock:
            cur = conn.execute(
                "UPDATE ngoai_le_ca_nhan SET dang_ap_dung=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (1 if is_active else 0, exception_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Không tìm thấy ngoại lệ.")
            conn.commit()
        return {
            "status": "ok",
            "is_active": is_active,
            "message": "Đã kích hoạt ngoại lệ." if is_active else "Đã ngừng áp dụng ngoại lệ.",
        }

    @app.delete("/api/exceptions/{exception_id}", dependencies=[Depends(require_admin)])
    def api_delete_exception(exception_id: int):
        conn = db.get_connection()
        with db.lock:
            cur = conn.execute("DELETE FROM ngoai_le_ca_nhan WHERE id=?", (exception_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Không tìm thấy ngoại lệ.")
            conn.commit()
        return {"status": "ok", "message": "Đã xóa ngoại lệ cá nhân."}

    # =========================================================
    # GĐ4-02C - Lịch sử tra cứu trong phiên
    # =========================================================

    @app.get("/api/history", dependencies=[Depends(require_admin)])
    def api_history():
        return {
            "total": len(SEARCH_HISTORY),
            "history": list(
                reversed(
                    SEARCH_HISTORY[-30:]
                )
            ),
        }

    # =========================================================
    # GĐ4-02C - Thông tin hệ thống / LAN
    # =========================================================

    @app.get("/api/system", dependencies=[Depends(require_admin)])
    def api_system():
        lan_ip = "127.0.0.1"

        sock = None

        try:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )

            sock.connect(
                ("8.8.8.8", 80)
            )

            lan_ip = sock.getsockname()[0]

        except OSError:
            pass

        finally:
            if sock is not None:
                sock.close()

        return {
            "server_status": "ONLINE",
            "database_status": "CONNECTED",

            "search_engine": "GD2-03",
            "rule_engine": "GD2-03",

            "input_reader": "GD3-01",
            "information_mapping": "GD3-02",
            "backend": "GD3-04",

            "version": "4.0.0",

            # UI hiện dùng field này để dựng URL LAN.
            "host_name": lan_ip,

            "machine_name":
                socket.gethostname(),

            "port": 8000,

            "lan_url":
                f"http://{lan_ip}:8000",
        }

    @app.post("/upload", dependencies=[Depends(require_admin)])
    async def upload(
        file: UploadFile = File(...),
        data_type: str = Form(DATA_TYPE),
    ):
        data_type = str(
            data_type or DATA_TYPE
        ).strip().upper()

        if data_type not in SUPPORTED_DATA_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Loại dữ liệu không hỗ trợ: "
                    f"{data_type}"
                ),
            )

        suffix = Path(file.filename or "").suffix.lower()
        structured_types = {"DON_VI", "BUSINESS_RULE", "NHAN_VIEN_CO_KET_QUA"}
        if data_type in structured_types and suffix not in {".csv", ".xlsx", ".txt"}:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Loại dữ liệu này cần file có cấu trúc CSV, XLSX hoặc TXT dạng bảng."
                ),
            )

        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Tệp rỗng.",
            )

        try:
            return _analyse_and_map(
                mapping_service(),
                content=content,
                filename=file.filename or "upload",
                raw_text=None,
                input_method="FILE",
                data_type=data_type,
            )

        except (
            InputAnalysisError,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    @app.post("/input", dependencies=[Depends(require_admin)])
    def input_string(payload: Dict[str, Any] = Body(...)):
        raw_text = payload.get("raw_text") or payload.get("text") or ""
        if not str(raw_text).strip():
            raise HTTPException(status_code=400, detail="String Input rỗng.")
        try:
            data_type = _extract_data_type(payload)
            if data_type not in {"NHAN_VIEN_KHONG_KET_QUA", "DON_VI"}:
                raise ValueError(
                    "Nhập thủ công tại màn Nhập dữ liệu chỉ hỗ trợ Hồ sơ nhân viên và Đơn vị. "
                    "Business Rule và Ngoại lệ cá nhân được nhập tại màn quản lý tương ứng."
                )
            return _analyse_and_map(
                mapping_service(),
                content=None,
                filename=None,
                raw_text=str(raw_text),
                input_method="RAW_STRING",
                data_type=data_type,
            )
        except (InputAnalysisError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/preview", dependencies=[Depends(require_admin)])
    def preview(
        payload: Dict[str, Any] = Body(...)
    ):
        rows = _extract_rows(payload)
        mapping_items = _extract_mapping(payload)

        try:
            data_type = _extract_data_type(payload)
        except ValueError as exc:
            return _error(
                400,
                str(exc),
            )

        if not rows:
            raise HTTPException(
                status_code=400,
                detail="Không có dữ liệu preview.",
            )

        if not mapping_items:
            raise HTTPException(
                status_code=400,
                detail="Thiếu mapping_items.",
            )

        summary = _mapping_summary(
            mapping_service(),
            mapping_items,
            data_type,
        )

        return {
            "status": "ok",
            "data_type": data_type,
            "preview_rows": rows[:15],
            "total": len(rows),
            "mapping_items": mapping_items,
            **summary,
        }

    @app.post("/mapping/confirm", dependencies=[Depends(require_admin)])
    def mapping_confirm(payload: Dict[str, Any] = Body(...)):
        mapping_items = _extract_mapping(payload)
        if not mapping_items:
            raise HTTPException(status_code=400, detail="mapping_items không hợp lệ.")

        try:
            data_type = _extract_data_type(payload)
        except ValueError as exc:
            return _error(
                400,
                str(exc),
            )

        source_column = str(payload.get("source_column") or "").strip()
        target_field = payload.get("target_field")
        confirm_all = bool(payload.get("confirm_all", False))
        confirmed = bool(payload.get("confirmed", True))

        allowed = {
            str(item["field"])
            for item in SCHEMA_FIELDS[data_type]
        }
        if target_field is not None and str(target_field) not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"target_field không hỗ trợ: {target_field}",
            )

        updated = []
        matched = False
        for original in mapping_items:
            item = dict(original)
            should_update = confirm_all or (
                source_column and str(item.get("source_column") or "") == source_column
            )
            if should_update:
                matched = True
                old_target = item.get("target_field")
                if target_field is not None:
                    item["target_field"] = str(target_field)
                    item["is_edited"] = str(target_field) != str(old_target)
                item["confirmed_by_user"] = confirmed
            updated.append(item)

        if not matched:
            raise HTTPException(status_code=404, detail="Không tìm thấy mapping cần xác nhận.")

        summary = _mapping_summary(
            mapping_service(),
            updated,
            data_type,
        )

        return {
            "status": "ok",
            "data_type": data_type,
            "confirmed": confirmed,
            "mapping_items": updated,
            **summary,
        }

    @app.post("/validation", dependencies=[Depends(require_admin)])
    def validation(payload: Dict[str, Any] = Body(...)):
        rows = _extract_rows(payload)
        mapping_items = _extract_mapping(payload)

        try:
            data_type = _extract_data_type(payload)
        except ValueError as exc:
            return _error(
                400,
                str(exc),
            )

        if not rows or not mapping_items:
            return _error(
                400,
                "Cần rows và mapping_items để Validation.",
            )

        result = validation_service().validate_dataset(
            rows=rows,
            mapping_items=mapping_items,
            data_type=data_type,
        )

        result = dict(result)
        result["data_type"] = data_type

        # Validation schema chỉ kiểm tra cấu trúc/định dạng. Với Business Rule
        # và Ngoại lệ, cần kiểm tra thêm đơn vị/nhân viên tham chiếu đã tồn tại.
        reference_errors = _reference_validation_errors(
            db, rows, mapping_items, data_type
        )
        if reference_errors:
            current_errors = list(result.get("errors") or [])
            current_errors.extend({
                "field": "REFERENCE",
                "row_idx": 0,
                "message": message,
                "type": "REFERENCE_NOT_FOUND",
            } for message in reference_errors)
            result["errors"] = current_errors
            result["reference_errors"] = reference_errors
            result["error_count"] = len(current_errors)
            result["status"] = "FAIL"
            result["can_commit"] = False
            checklist = list(result.get("checklist") or [])
            checklist.append({
                "name": "Tham chiếu dữ liệu",
                "passed": False,
                "detail": "Có đơn vị/nhân viên tham chiếu chưa tồn tại",
            })
            result["checklist"] = checklist

        status_code = (
            200
            if result.get("status") == "PASS"
            else 422
        )

        return JSONResponse(
            status_code=status_code,
            content=result,
        )

    @app.post("/commit", dependencies=[Depends(require_admin)])
    def commit(payload: Dict[str, Any] = Body(...)):
        rows = _extract_rows(payload)
        mapping_items = _extract_mapping(payload)

        mode = str(
            payload.get("mode")
            or "APPEND"
        ).strip().upper()

        try:
            data_type = _extract_data_type(payload)
        except ValueError as exc:
            return _error(
                400,
                str(exc),
            )

        if mode not in {
            "APPEND",
            "UPSERT",
            "REPLACE",
        }:
            return _error(
                400,
                f"Chế độ nạp không hợp lệ: {mode}",
            )

        if not rows or not mapping_items:
            return _error(
                400,
                "Cần rows và mapping_items để Commit.",
            )

        # Luôn Validation lại trước khi ghi DB.
        validation_result = (
            validation_service()
            .validate_dataset(
                rows=rows,
                mapping_items=mapping_items,
                data_type=data_type,
            )
        )

        if not validation_result.get(
            "can_commit"
        ):
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "message":
                        "Validation FAIL. Không được Commit.",
                    "data_type":
                        data_type,
                    "validation":
                        validation_result,
                },
            )

        reference_errors = _reference_validation_errors(
            db, rows, mapping_items, data_type
        )
        if reference_errors:
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "message": "Validation tham chiếu FAIL. Không được Commit.",
                    "data_type": data_type,
                    "validation": validation_result,
                    "reference_errors": reference_errors,
                },
            )

        try:
            with db.lock:
                result = (
                    CommitService.commit_dataset(
                        db.get_connection(),
                        rows=rows,
                        mapping_items=mapping_items,
                        data_type=data_type,
                        mode=mode,
                    )
                )

        except (ValueError, RuntimeError) as exc:
            return _error(
                500,
                str(exc),
                data_type=data_type,
                rolled_back=True,
            )

        if data_type == "NHAN_VIEN_KHONG_KET_QUA":
            code_source = None
            for item in mapping_items:
                if str(item.get("target_field") or "") == "MA_NHAN_VIEN":
                    code_source = str(item.get("source_column") or "")
                    break
            employee_codes = [
                str(row.get(code_source) or "").strip()
                for row in rows
                if code_source and str(row.get(code_source) or "").strip()
            ]
            account_sync = app.state.auth_service.ensure_employee_accounts(employee_codes)
            result = dict(result)
            result["account_sync"] = account_sync
            result["warnings"] = account_sync.get("warnings", [])

        return {
            "status": "success",
            "data_type": data_type,
            "mode": mode,
            "validation": validation_result,
            "commit": result,
        }

    def _with_business_status(items: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
        enriched = []
        for item in items:
            current = dict(item)
            if kind == "employee" and current.get("ma_nhan_vien"):
                current["business_status"] = app.state.rule_engine.evaluate_employee_salary_rule(
                    current["ma_nhan_vien"]
                )
            elif kind == "unit" and current.get("ma_don_vi"):
                current["business_status"] = app.state.rule_engine.evaluate_unit_salary_rule(
                    current["ma_don_vi"]
                )
            enriched.append(current)
        return enriched

    @app.get("/search")
    def search(
        q: str = Query(..., min_length=1),
        kind: str = Query("employee", pattern="^(employee|unit)$"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        offset: Optional[int] = Query(None, ge=0),
        include_status: bool = Query(True),
        auth_user: Dict[str, Any] = Depends(require_ready_user),
    ):
        actual_offset = offset if offset is not None else (page - 1) * limit
        if kind == "employee":
            result = app.state.search_engine.search_nhan_vien(
                q, page=page, limit=limit, offset=actual_offset
            )
        else:
            result = app.state.search_engine.search_don_vi(
                q, page=page, limit=limit, offset=actual_offset
            )
        if include_status:
            result = dict(result)

            result["ket_qua"] = (
                _with_business_status(
                    result.get(
                        "ket_qua",
                        [],
                    ),
                    kind,
                )
            )

            result["data"] = (
                result["ket_qua"]
            )

        result["kind"] = kind

        # ---------------------------------------------
        # GĐ4 - lưu lịch sử tra cứu trong phiên
        # ---------------------------------------------

        items = result.get(
            "ket_qua",
            [],
        )

        if items:
            first = items[0]

            business_status = (
                first.get("business_status")
                or {}
            )

            if kind == "employee":
                object_name = (
                    first.get("ho_ten")
                    or first.get(
                        "ma_nhan_vien"
                    )
                    or q
                )

                object_type = "Cá nhân"

            else:
                object_name = (
                    first.get("ten_don_vi")
                    or first.get(
                        "ma_don_vi"
                    )
                    or q
                )

                object_type = "Đơn vị"

            history_item = {
                "query_id":
                    f"Q{len(SEARCH_HISTORY) + 1:04d}",

                "user":
                    auth_user.get("username") or "UNKNOWN",

                "query":
                    q,

                "object_name":
                    object_name,

                "object_type":
                    object_type,

                "result":
                    business_status.get(
                        "ket_qua",
                        "CHUA_XAC_DINH",
                    ),

                "rule":
                    business_status.get(
                        "ma_quy_tac"
                    )
                    or "N/A",

                "timestamp":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
            }

            SEARCH_HISTORY.append(
                history_item
            )

            # Chỉ giữ tối đa 100 lượt gần nhất.
            if len(SEARCH_HISTORY) > 100:
                del SEARCH_HISTORY[:-100]

        return result

    @app.get("/details/{kind}/{identifier}")
    def details(
        kind: str,
        identifier: str,
        auth_user: Dict[str, Any] = Depends(require_ready_user),
    ):
        conn = db.get_connection()
        with db.lock:
            if kind == "employee":
                row = conn.execute(
                    "SELECT nv.*, dv.loai_don_vi, dv.ten_don_vi AS ten_don_vi_thuc "
                    "FROM nhan_vien nv LEFT JOIN don_vi dv ON dv.ma_don_vi=nv.ma_don_vi "
                    "WHERE upper(nv.ma_nhan_vien)=upper(?)",
                    (identifier,),
                ).fetchone()
            elif kind == "unit":
                row = conn.execute(
                    "SELECT * FROM don_vi WHERE upper(ma_don_vi)=upper(?)",
                    (identifier,),
                ).fetchone()
            else:
                raise HTTPException(status_code=400, detail="kind phải là employee hoặc unit.")

        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đối tượng.")

        status_result = (
            app.state.rule_engine.evaluate_employee_salary_rule(identifier)
            if kind == "employee"
            else app.state.rule_engine.evaluate_unit_salary_rule(identifier)
        )
        row_data = _row_dict(row)
        if auth_user.get("role") != "ADMIN":
            if kind == "employee":
                allowed = {
                    "ma_nhan_vien", "ho_ten", "ma_don_vi", "ten_don_vi",
                    "don_vi", "chuc_vu", "loai_don_vi", "ten_don_vi_thuc",
                }
            else:
                allowed = {"ma_don_vi", "ten_don_vi", "loai_don_vi"}
            row_data = {key: value for key, value in row_data.items() if key in allowed}
        return {
            "status": "ok",
            "kind": kind,
            "data": row_data,
            "business_status": status_result,
        }

    @app.get("/status/{kind}/{identifier}")
    def status(
        kind: str,
        identifier: str,
        date: Optional[str] = Query(None),
        auth_user: Dict[str, Any] = Depends(require_ready_user),
    ):
        if kind == "employee":
            result = app.state.rule_engine.evaluate_employee_salary_rule(identifier, date)
        elif kind == "unit":
            result = app.state.rule_engine.evaluate_unit_salary_rule(identifier, date)
        else:
            raise HTTPException(status_code=400, detail="kind phải là employee hoặc unit.")
        return {
            "status": "ok",
            "kind": kind,
            "identifier": identifier,
            "business_status": result,
        }

    @app.get("/export", dependencies=[Depends(require_admin)])
    def export_search(
        q: str = Query(..., min_length=1),
        kind: str = Query("employee", pattern="^(employee|unit)$"),
        format: str = Query("csv", pattern="^(csv|xlsx|json)$"),
        limit: int = Query(1000, ge=1, le=1000),
    ):
        query_text = (q or "").strip()

        # Frontend dùng q=all khi người dùng chưa nhập từ khóa. Khi đó export
        # toàn bộ đối tượng của scope thay vì tìm literal từ "all".
        if query_text.lower() == "all":
            conn = db.get_connection()
            with db.lock:
                if kind == "employee":
                    raw_rows = conn.execute(
                        "SELECT * FROM nhan_vien ORDER BY id LIMIT ?",
                        (limit,),
                    ).fetchall()
                    base_rows = []
                    for raw in raw_rows:
                        item = _row_dict(raw)
                        item.setdefault("ten_don_vi", item.get("don_vi") or "")
                        item.setdefault("loai_khop", "ALL")
                        item.setdefault("do_khop", 1.0)
                        base_rows.append(item)
                else:
                    raw_rows = conn.execute(
                        "SELECT * FROM don_vi ORDER BY id LIMIT ?",
                        (limit,),
                    ).fetchall()
                    base_rows = []
                    for raw in raw_rows:
                        item = _row_dict(raw)
                        item.setdefault("loai_khop", "ALL")
                        item.setdefault("do_khop", 1.0)
                        base_rows.append(item)
            rows = _with_business_status(base_rows, kind)
        else:
            if kind == "employee":
                search_result = app.state.search_engine.search_nhan_vien(query_text, limit=limit, offset=0)
            else:
                search_result = app.state.search_engine.search_don_vi(query_text, limit=limit, offset=0)
            rows = _with_business_status(search_result.get("ket_qua", []), kind)

        if kind == "employee":
            header = ["ma_nhan_vien", "ho_ten", "ma_don_vi", "ten_don_vi", "loai_khop", "do_khop", "ket_qua", "can_cu"]
        else:
            header = ["ma_don_vi", "ten_don_vi", "loai_don_vi", "loai_khop", "do_khop", "ket_qua", "can_cu"]

        flat_rows = []
        for row in rows:
            status_data = row.get("business_status") or {}
            flat_rows.append({
                **row,
                "ket_qua": status_data.get("ket_qua"),
                "can_cu": status_data.get("can_cu"),
            })

        if format == "json":
            return {"status": "ok", "query": q, "kind": kind, "data": flat_rows}

        if format == "xlsx":
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Ket_Qua_Tra_Cuu"
            ws.append(header)
            for row in flat_rows:
                ws.append([row.get(column, "") for column in header])

            # Chỉ định dạng nhẹ để file tải về đọc được ngay.
            for cell in ws[1]:
                cell.font = openpyxl.styles.Font(bold=True)
            ws.freeze_panes = "A2"
            for column_cells in ws.columns:
                width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 45)
                ws.column_dimensions[column_cells[0].column_letter].width = max(width, 12)

            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            filename = f"payrollcheck_{kind}_export.xlsx"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers=headers,
            )

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)

        filename = f"payrollcheck_{kind}_export.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        data = buffer.getvalue().encode("utf-8-sig")
        return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers=headers)

    return app


app = create_app()
