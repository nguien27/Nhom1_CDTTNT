from pathlib import Path
import sqlite3


class SQLiteRepository:
    """
    Quản lý kết nối SQLite cho GĐ2-03.

    Ưu tiên:
    1. sql/schema.sql ở root repo
    2. sql/schema.sql trong chính GĐ2-03
    """

    def __init__(self, db_path=":memory:", schema_path=None):
        self.db_path = db_path

        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

        self.connection.execute("PRAGMA foreign_keys = ON")

        self.khoi_tao_database(schema_path)

    def get_connection(self):
        return self.connection

    def tim_schema(self, schema_path=None):
        if schema_path:
            path = Path(schema_path)

            if path.exists():
                return path

        file_hien_tai = Path(__file__).resolve()

        # src/repository.py
        # -> gd2_03_search_rule_engine
        thu_muc_gd2_03 = file_hien_tai.parents[1]

        # -> experiments
        # -> root project
        root_project = file_hien_tai.parents[3]

        danh_sach = [
            root_project / "sql" / "schema.sql",
            thu_muc_gd2_03 / "sql" / "schema.sql",
        ]

        for path in danh_sach:
            if path.exists():
                return path

        raise FileNotFoundError(
            "Không tìm thấy sql/schema.sql."
        )

    def khoi_tao_database(self, schema_path=None):
        path_schema = self.tim_schema(schema_path)

        noi_dung_schema = path_schema.read_text(
            encoding="utf-8"
        )

        self.connection.executescript(noi_dung_schema)

        # Bảng ngoại lệ cá nhân cần cho Rule Engine.
        # CREATE IF NOT EXISTS nên không ảnh hưởng nếu root đã có bảng.
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ngoai_le_ca_nhan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ma_quy_tac TEXT,
                ma_nhan_vien TEXT NOT NULL,

                ket_qua TEXT NOT NULL
                    CHECK (ket_qua IN ('YES', 'NO')),

                can_cu TEXT,

                muc_uu_tien INTEGER NOT NULL DEFAULT 0,

                ngay_hieu_luc TEXT,
                ngay_het_hieu_luc TEXT,

                dang_ap_dung INTEGER NOT NULL DEFAULT 1
                    CHECK (dang_ap_dung IN (0, 1)),

                ghi_chu TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (ma_nhan_vien)
                    REFERENCES nhan_vien(ma_nhan_vien)
            );

            CREATE INDEX IF NOT EXISTS
                idx_nhan_vien_ma_nhan_vien
                ON nhan_vien(ma_nhan_vien);

            CREATE INDEX IF NOT EXISTS
                idx_ngoai_le_ma_nhan_vien
                ON ngoai_le_ca_nhan(ma_nhan_vien);
            """
        )

        self.connection.commit()

    def execute_query(self, cau_lenh, tham_so=()):
        cursor = self.connection.execute(
            cau_lenh,
            tham_so,
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    def execute(self, cau_lenh, tham_so=()):
        self.connection.execute(
            cau_lenh,
            tham_so,
        )

        self.connection.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()