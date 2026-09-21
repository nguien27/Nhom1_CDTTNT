"""SQLite lifecycle cho GĐ3-04.

Schema là schema tích hợp tương thích GĐ2-03 Search/Rule và GĐ3-03 Commit.
Business logic không nằm ở đây. Auth schema được kiểm tra thêm ở runtime để
DB cũ vẫn tự nâng cấp khi chạy release mới.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "runtime" / "gd3_04_backend_validation.db"
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"


class Database:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.lock = RLock()

        if self.db_path != ":memory:":
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize_schema()

    def initialize_schema(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.lock:
            self.connection.executescript(schema)
            self._ensure_auth_schema_runtime()
            self.connection.commit()

    def _ensure_auth_schema_runtime(self) -> None:
        """Đảm bảo DB runtime cũ có schema account/session cần thiết.

        Không chỉ dựa vào schema.sql: release có thể được chạy trên file SQLite
        đã tồn tại từ trước GĐ4 auth.
        """
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMIN','USER')),
                ma_nhan_vien TEXT UNIQUE,
                email TEXT,
                must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0,1)),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_users_ma_nhan_vien ON users(ma_nhan_vien);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);
            """
        )

        # Migration mềm nếu có DB thử nghiệm từng tạo bảng users thiếu cột.
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(users)").fetchall()
        }
        additions = {
            "ma_nhan_vien": "TEXT",
            "email": "TEXT",
            "must_change_password": "INTEGER NOT NULL DEFAULT 0",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE users ADD COLUMN {name} {definition}"
                )

        # Nhân viên có trạng thái hoạt động riêng để ADMIN có thể ngừng/kích hoạt
        # hồ sơ mà không xóa lịch sử. DB cũ được bổ sung cột tự động.
        employee_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(nhan_vien)").fetchall()
        }
        if "is_active" not in employee_columns:
            self.connection.execute(
                "ALTER TABLE nhan_vien ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

    def get_connection(self) -> sqlite3.Connection:
        return self.connection

    def close(self) -> None:
        with self.lock:
            self.connection.close()


def get_database(db_path: str | Path | None = None) -> Database:
    return Database(db_path)
