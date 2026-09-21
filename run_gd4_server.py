from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


# =========================================================
# Đường dẫn project
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent

GD3_04_DIR = (
    ROOT_DIR
    / "experiments"
    / "gd3_04_backend_validation"
)


# Cho phép import app.main của GĐ3-04
for path in (ROOT_DIR, GD3_04_DIR):
    path_str = str(path)

    if path_str not in sys.path:
        sys.path.insert(0, path_str)


# =========================================================
# Cấu hình server GĐ4
# =========================================================

HOST = os.getenv(
    "GD4_HOST",
    "0.0.0.0",
)

PORT = int(
    os.getenv(
        "GD4_PORT",
        "8000",
    )
)


# =========================================================
# Entry point duy nhất của GĐ4
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PAYROLLCHECK - HE THONG TRA CUU CHI TRA LUONG")
    print("=" * 60)

    print(f"Server : http://127.0.0.1:{PORT}")
    print(f"Health : http://127.0.0.1:{PORT}/health")
    print(f"Docs   : http://127.0.0.1:{PORT}/docs")

    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
    )