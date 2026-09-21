from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, Iterable

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 240_000
SESSION_COOKIE_NAME = "payrollcheck_session"
SESSION_HOURS = int(os.getenv("PAYROLLCHECK_SESSION_HOURS", "12"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    value = str(password or "")
    if not value:
        raise ValueError("Mật khẩu không được để trống.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        salt,
        iterations,
    )
    return f"{PASSWORD_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_hex, digest_hex = str(stored_hash).split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def initial_password_from_email(email: str) -> str | None:
    value = str(email or "").strip()
    if "@" not in value:
        return None
    local_part = value.split("@", 1)[0].strip()
    return local_part or None


class AuthService:
    def __init__(self, conn: sqlite3.Connection, lock: RLock):
        self.conn = conn
        self.lock = lock

    @staticmethod
    def _row_dict(row: sqlite3.Row | None) -> Dict[str, Any] | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def public_user(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        get = row.get if isinstance(row, dict) else row.__getitem__
        return {
            "id": get("id"),
            "username": get("username"),
            "role": get("role"),
            "ma_nhan_vien": get("ma_nhan_vien"),
            "email": get("email"),
            "must_change_password": bool(get("must_change_password")),
            "is_active": bool(get("is_active")),
        }

    def ensure_admin_from_env(self) -> Dict[str, Any]:
        username = os.getenv("PAYROLLCHECK_ADMIN_USERNAME", "admin").strip() or "admin"
        password = os.getenv("PAYROLLCHECK_ADMIN_PASSWORD", "Admin@123")
        email = os.getenv("PAYROLLCHECK_ADMIN_EMAIL", "").strip() or None

        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE lower(username)=lower(?)",
                (username,),
            ).fetchone()
            if row is None:
                self.conn.execute(
                    """
                    INSERT INTO users(
                        username, password_hash, role, ma_nhan_vien, email,
                        must_change_password, is_active
                    ) VALUES(?,?, 'ADMIN', NULL, ?, 0, 1)
                    """,
                    (username, hash_password(password), email),
                )
                self.conn.commit()
                row = self.conn.execute(
                    "SELECT * FROM users WHERE lower(username)=lower(?)",
                    (username,),
                ).fetchone()
            return self.public_user(row)

    def authenticate(self, username: str, password: str) -> Dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE lower(username)=lower(?)",
                (str(username or "").strip(),),
            ).fetchone()
        if row is None or not bool(row["is_active"]):
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return self.public_user(row)

    def create_session(self, user_id: int) -> str:
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = _utc_now()
        expires = now + timedelta(hours=SESSION_HOURS)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO auth_sessions(
                    token_hash, user_id, created_at, expires_at, last_seen_at
                ) VALUES(?,?,?,?,?)
                """,
                (token_hash, int(user_id), _iso(now), _iso(expires), _iso(now)),
            )
            self.conn.commit()
        return raw_token

    def get_user_by_session(self, raw_token: str | None) -> Dict[str, Any] | None:
        if not raw_token:
            return None
        token_hash = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
        now = _utc_now()
        with self.lock:
            row = self.conn.execute(
                """
                SELECT u.*
                FROM auth_sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=?
                  AND s.revoked_at IS NULL
                  AND s.expires_at>?
                  AND u.is_active=1
                """,
                (token_hash, _iso(now)),
            ).fetchone()
            if row is not None:
                self.conn.execute(
                    "UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?",
                    (_iso(now), token_hash),
                )
                self.conn.commit()
        return self.public_user(row) if row is not None else None

    def revoke_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token_hash = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
        with self.lock:
            self.conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (_iso(_utc_now()), token_hash),
            )
            self.conn.commit()

    def change_password(self, user_id: int, current_password: str, new_password: str) -> Dict[str, Any]:
        new_value = str(new_password or "")
        if len(new_value) < 6:
            raise ValueError("Mật khẩu mới phải có ít nhất 6 ký tự.")
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE id=?",
                (int(user_id),),
            ).fetchone()
            if row is None:
                raise ValueError("Không tìm thấy tài khoản.")
            if not verify_password(current_password, row["password_hash"]):
                raise ValueError("Mật khẩu hiện tại không đúng.")
            if verify_password(new_value, row["password_hash"]):
                raise ValueError("Mật khẩu mới phải khác mật khẩu hiện tại.")
            self.conn.execute(
                """
                UPDATE users
                SET password_hash=?, must_change_password=0,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (hash_password(new_value), int(user_id)),
            )
            self.conn.commit()
            updated = self.conn.execute(
                "SELECT * FROM users WHERE id=?",
                (int(user_id),),
            ).fetchone()
        return self.public_user(updated)

    def ensure_employee_accounts(
        self,
        employee_codes: Iterable[str],
    ) -> Dict[str, Any]:
        created: list[str] = []
        existing: list[str] = []
        warnings: list[Dict[str, str]] = []

        seen: set[str] = set()
        with self.lock:
            for code in employee_codes:
                ma = str(code or "").strip()
                if not ma or ma.upper() in seen:
                    continue
                seen.add(ma.upper())

                employee = self.conn.execute(
                    "SELECT ma_nhan_vien, email FROM nhan_vien WHERE upper(ma_nhan_vien)=upper(?)",
                    (ma,),
                ).fetchone()
                if employee is None:
                    continue

                account = self.conn.execute(
                    "SELECT id FROM users WHERE lower(username)=lower(?) OR upper(ma_nhan_vien)=upper(?)",
                    (employee["ma_nhan_vien"], employee["ma_nhan_vien"]),
                ).fetchone()
                if account is not None:
                    existing.append(employee["ma_nhan_vien"])
                    # Chỉ đồng bộ email mô tả; tuyệt đối không reset password.
                    self.conn.execute(
                        """
                        UPDATE users
                        SET email=?, updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                        """,
                        (employee["email"], account["id"]),
                    )
                    continue

                email = str(employee["email"] or "").strip()
                initial_password = initial_password_from_email(email)
                if not initial_password:
                    warnings.append({
                        "ma_nhan_vien": employee["ma_nhan_vien"],
                        "warning": "Nhân viên chưa có EMAIL hợp lệ nên chưa tạo tài khoản USER.",
                    })
                    continue

                try:
                    self.conn.execute(
                        """
                        INSERT INTO users(
                            username, password_hash, role, ma_nhan_vien, email,
                            must_change_password, is_active
                        ) VALUES(?,?, 'USER', ?, ?, 1, 1)
                        """,
                        (
                            employee["ma_nhan_vien"],
                            hash_password(initial_password),
                            employee["ma_nhan_vien"],
                            email,
                        ),
                    )
                    created.append(employee["ma_nhan_vien"])
                except sqlite3.IntegrityError as exc:
                    warnings.append({
                        "ma_nhan_vien": employee["ma_nhan_vien"],
                        "warning": f"Không thể tạo account tự động: {exc}",
                    })
            self.conn.commit()

        return {
            "created": created,
            "existing": existing,
            "warnings": warnings,
            "created_count": len(created),
            "existing_count": len(existing),
            "warning_count": len(warnings),
        }
