from __future__ import annotations
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .normalization import chuan_hoa_tim_kiem, chuan_hoa_ten_don_vi

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "runtime" / "gd2_04.db"
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def ensure_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


def tao_ma_don_vi_noi_bo(ten_don_vi: str) -> str:
    norm = chuan_hoa_tim_kiem(ten_don_vi)
    digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:10].upper()
    return f"DV_{digest}"


def ensure_unit(conn: sqlite3.Connection, ten_don_vi: str, loai_don_vi: str | None = None) -> str:
    ten = chuan_hoa_ten_don_vi(ten_don_vi)
    ten_chuan = chuan_hoa_tim_kiem(ten)
    row = conn.execute("SELECT ma_don_vi FROM don_vi WHERE ten_don_vi_chuan = ?", (ten_chuan,)).fetchone()
    if row:
        if loai_don_vi:
            conn.execute(
                "UPDATE don_vi SET loai_don_vi = COALESCE(NULLIF(?,''), loai_don_vi), updated_at=CURRENT_TIMESTAMP WHERE ma_don_vi = ?",
                (loai_don_vi, row["ma_don_vi"]),
            )
        return row["ma_don_vi"]
    ma = tao_ma_don_vi_noi_bo(ten)
    conn.execute(
        "INSERT INTO don_vi(ma_don_vi,ten_don_vi,ten_don_vi_chuan,loai_don_vi) VALUES(?,?,?,?)",
        (ma, ten, ten_chuan, loai_don_vi or None),
    )
    return ma


class ConnectionRepositoryAdapter:
    """Adapter DB mỏng cho GĐ2-03; không chứa Search/Rule logic."""
    def __init__(self, conn: sqlite3.Connection):
        self.connection = conn

    def get_connection(self) -> sqlite3.Connection:
        return self.connection

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cur = self.connection.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def execute(self, query: str, params: tuple = ()) -> None:
        self.connection.execute(query, params)
