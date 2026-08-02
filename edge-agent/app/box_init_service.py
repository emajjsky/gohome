from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterator, Optional
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import socket

from .settings import settings


ADMIN_SESSION_COOKIE = "gohome_admin_session"
DEFAULT_ADMIN_USERNAME = "admin"
LEGACY_DEFAULT_ADMIN_PASSWORD = "123456"
ADMIN_SESSION_HOURS = 12
ADMIN_MAX_SESSIONS = 16
ADMIN_FAILURE_WINDOW_SECONDS = 15 * 60
ADMIN_MAX_LOCK_SECONDS = 5 * 60
ADMIN_AUDIT_LIMIT = 1000


class AdminLoginThrottled(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(f"Admin login is locked for {self.retry_after_seconds} seconds")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 180_000)
    return derived.hex()


class BoxInitService:
    def __init__(
        self,
        app_settings: Any,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.settings = app_settings
        self._clock = clock
        self._thread_lock = RLock()
        self.state_path = Path(self.settings.data_dir) / "box_state.json"
        self.admin_auth_path = Path(self.settings.data_dir) / "admin_auth.json"
        self.admin_sessions_path = Path(self.settings.data_dir) / "admin_sessions.json"
        self.admin_attempts_path = Path(self.settings.data_dir) / "admin_auth_attempts.json"
        self.admin_audit_path = Path(self.settings.data_dir) / "admin_security_audit.json"
        self.admin_credential_path = Path(self.settings.data_dir) / "admin_setup_credential.txt"
        self.admin_lock_path = Path(self.settings.data_dir) / ".admin_auth.lock"
        self.init_marker_path = Path(self.settings.data_dir) / ".box_initialized"

    def _now(self) -> datetime:
        current = self._clock()
        return current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)

    def _iso_now(self) -> str:
        return self._now().isoformat()

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        Path(self.settings.data_dir).mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with self.admin_lock_path.open("a+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _read_json_unlocked(self, path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return dict(fallback)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else dict(fallback)
        except (OSError, json.JSONDecodeError):
            return dict(fallback)

    def _write_json_unlocked(self, path: Path, payload: Dict[str, Any], *, mode: int = 0o600) -> None:
        self._write_text_unlocked(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            mode=mode,
        )

    def _write_text_unlocked(self, path: Path, value: str, *, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            tmp_path.write_text(value, encoding="utf-8")
            tmp_path.chmod(mode)
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _append_audit_unlocked(
        self,
        event: str,
        *,
        username: str = "",
        client_ip: str = "",
        detail: Dict[str, Any] | None = None,
    ) -> None:
        payload = self._read_json_unlocked(self.admin_audit_path, {"records": []})
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        records.append({
            "event": str(event),
            "username": str(username)[:40],
            "client_ip": str(client_ip)[:80],
            "occurred_at": self._iso_now(),
            "detail": dict(detail or {}),
        })
        self._write_json_unlocked(self.admin_audit_path, {"records": records[-ADMIN_AUDIT_LIMIT:]})

    def _device_id_path(self) -> Path:
        return Path(self.settings.data_dir) / "device_id.txt"

    def _ensure_device_id_unlocked(self) -> str:
        path = self._device_id_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        device_id = f"edge-{secrets.token_hex(8)}"
        self._write_text_unlocked(path, device_id)
        return device_id

    def ensure_device_id(self) -> str:
        with self._exclusive():
            return self._ensure_device_id_unlocked()

    def _write_setup_credential_unlocked(self, password: str) -> None:
        self._write_text_unlocked(self.admin_credential_path, f"{password}\n")

    def _new_setup_credential(self) -> str:
        return secrets.token_urlsafe(15)

    def reset_admin_password(
        self,
        *,
        username: str = DEFAULT_ADMIN_USERNAME,
        password: str | None = None,
        must_change_password: bool = True,
    ) -> Dict[str, Any]:
        with self._exclusive():
            return self._reset_admin_password_unlocked(
                username=username,
                password=password,
                must_change_password=must_change_password,
            )

    def _reset_admin_password_unlocked(
        self,
        *,
        username: str,
        password: str | None,
        must_change_password: bool,
    ) -> Dict[str, Any]:
        generated = password is None
        if password is not None and (len(password) < 10 or password == LEGACY_DEFAULT_ADMIN_PASSWORD):
            raise ValueError("Operator-supplied admin password must be at least 10 characters and non-default")
        resolved_password = password or self._new_setup_credential()
        salt = secrets.token_hex(16)
        payload = {
            "username": username,
            "password_hash": password_hash(resolved_password, salt),
            "salt": salt,
            "must_change_password": True if generated else bool(must_change_password),
            "credential_kind": "generated_one_time" if generated else "operator_supplied",
            "password_changed_at": "",
            "updated_at": self._iso_now(),
        }
        self._write_json_unlocked(self.admin_auth_path, payload)
        self._write_json_unlocked(self.admin_sessions_path, {"sessions": []})
        self._write_json_unlocked(self.admin_attempts_path, {"attempts": {}})
        if generated:
            self._write_setup_credential_unlocked(resolved_password)
        else:
            self.admin_credential_path.unlink(missing_ok=True)
        self._append_audit_unlocked(
            "admin_credential_generated" if generated else "admin_credential_reset",
            username=username,
            detail={"must_change_password": payload["must_change_password"]},
        )
        return payload

    def _uses_legacy_default_unlocked(self, admin: Dict[str, Any]) -> bool:
        if admin.get("credential_kind"):
            return False
        salt = str(admin.get("salt") or "")
        stored_hash = str(admin.get("password_hash") or "")
        if not salt or not stored_hash:
            return False
        candidate = password_hash(LEGACY_DEFAULT_ADMIN_PASSWORD, salt)
        return hmac.compare_digest(candidate, stored_hash)

    def initialize(
        self,
        *,
        reset_admin: bool = False,
        username: str = DEFAULT_ADMIN_USERNAME,
        password: str | None = None,
        must_change_password: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if must_change_password is None:
            must_change_password = True
        self.settings.ensure_dirs()
        with self._exclusive():
            device_id = self._ensure_device_id_unlocked()
            state = self._read_json_unlocked(self.state_path, {})
            previous_state = dict(state)
            now = self._iso_now()
            if not state.get("initialized"):
                state = {
                    "initialized": True,
                    "initialized_at": now,
                    "device_id": device_id,
                    "device_name": socket.gethostname(),
                    "mdns_name": "gohome.local",
                    "admin_username": username,
                    "setup_version": 2,
                }
            else:
                state.update({
                    "initialized": True,
                    "device_id": state.get("device_id") or device_id,
                    "device_name": socket.gethostname(),
                    "mdns_name": state.get("mdns_name") or "gohome.local",
                    "admin_username": state.get("admin_username") or username,
                    "setup_version": 2,
                })
                state.pop("admin_default_password_set", None)
            comparable_state = {key: value for key, value in state.items() if key != "updated_at"}
            comparable_previous = {key: value for key, value in previous_state.items() if key != "updated_at"}
            if comparable_state != comparable_previous:
                state["updated_at"] = now
                self._write_json_unlocked(self.state_path, state)
            if not self.init_marker_path.exists():
                self.init_marker_path.write_text(now, encoding="utf-8")

            admin = self._read_json_unlocked(self.admin_auth_path, {})
            rotate_legacy = bool(admin) and self._uses_legacy_default_unlocked(admin)
            admin_valid = all(admin.get(key) for key in ("username", "salt", "password_hash"))
            if reset_admin or not admin_valid or rotate_legacy:
                self._reset_admin_password_unlocked(
                    username=username,
                    password=password if reset_admin else None,
                    must_change_password=must_change_password,
                )
                if rotate_legacy:
                    self._append_audit_unlocked("legacy_default_credential_rotated", username=username)
            elif not admin.get("credential_kind"):
                admin["credential_kind"] = "legacy_user_defined"
                admin["updated_at"] = now
                self._write_json_unlocked(self.admin_auth_path, admin)

            return self._status_unlocked("")

    def initialize_if_needed(self) -> None:
        with self._exclusive():
            state = self._read_json_unlocked(self.state_path, {})
            admin = self._read_json_unlocked(self.admin_auth_path, {})
            ready = (
                bool(state.get("initialized"))
                and int(state.get("setup_version") or 0) >= 2
                and all(admin.get(key) for key in ("username", "salt", "password_hash", "credential_kind"))
            )
        if not ready:
            self.initialize(reset_admin=False)

    def status(self, token: str = "") -> Dict[str, Any]:
        self.initialize_if_needed()
        with self._exclusive():
            return self._status_unlocked(token)

    def _status_unlocked(self, token: str) -> Dict[str, Any]:
        state = self._read_json_unlocked(self.state_path, {})
        admin = self._read_json_unlocked(self.admin_auth_path, {})
        session = self._session_status_unlocked(token) if token else None
        return {
            "initialized": bool(state.get("initialized")),
            "device_id": state.get("device_id") or self._ensure_device_id_unlocked(),
            "device_name": socket.gethostname(),
            "mdns_name": state.get("mdns_name") or "gohome.local",
            "admin_username": admin.get("username") or DEFAULT_ADMIN_USERNAME,
            "must_change_password": bool(admin.get("must_change_password", True)) if session else False,
            "authenticated": bool(session),
            "session": session or None,
            "initialized_at": state.get("initialized_at") or "",
            "updated_at": state.get("updated_at") or "",
        }

    def _verify_password_unlocked(self, username: str, password: str) -> bool:
        admin = self._read_json_unlocked(self.admin_auth_path, {})
        expected_username = str(admin.get("username") or DEFAULT_ADMIN_USERNAME)
        salt = str(admin.get("salt") or "")
        stored_hash = str(admin.get("password_hash") or "")
        if username != expected_username or not salt or not stored_hash:
            return False
        actual_hash = password_hash(password, salt)
        return hmac.compare_digest(actual_hash, stored_hash)

    def _attempt_key(self, username: str, client_ip: str) -> str:
        return token_hash(f"{username.strip().lower()}\x00{client_ip.strip() or 'unknown'}")

    def _parse_time(self, value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    def _active_attempts_unlocked(self) -> Dict[str, Dict[str, Any]]:
        payload = self._read_json_unlocked(self.admin_attempts_path, {"attempts": {}})
        source = payload.get("attempts") if isinstance(payload.get("attempts"), dict) else {}
        cutoff = self._now() - timedelta(seconds=ADMIN_FAILURE_WINDOW_SECONDS)
        active: Dict[str, Dict[str, Any]] = {}
        for key, value in source.items():
            if not isinstance(value, dict):
                continue
            last_failed_at = self._parse_time(str(value.get("last_failed_at") or ""))
            locked_until = self._parse_time(str(value.get("locked_until") or ""))
            if (last_failed_at and last_failed_at >= cutoff) or (locked_until and locked_until > self._now()):
                active[str(key)] = dict(value)
        return active

    def _retry_after(self, attempt: Dict[str, Any]) -> int:
        locked_until = self._parse_time(str(attempt.get("locked_until") or ""))
        if locked_until is None:
            return 0
        return max(0, int((locked_until - self._now()).total_seconds() + 0.999))

    def _record_failure_unlocked(self, username: str, client_ip: str) -> int:
        attempts = self._active_attempts_unlocked()
        key = self._attempt_key(username, client_ip)
        previous = attempts.get(key) or {}
        count = int(previous.get("failure_count") or 0) + 1
        lock_seconds = 0 if count < 3 else min(ADMIN_MAX_LOCK_SECONDS, 2 ** (count - 3))
        attempts[key] = {
            "failure_count": count,
            "last_failed_at": self._iso_now(),
            "locked_until": (
                (self._now() + timedelta(seconds=lock_seconds)).isoformat()
                if lock_seconds
                else ""
            ),
        }
        self._write_json_unlocked(self.admin_attempts_path, {"attempts": attempts})
        self._append_audit_unlocked(
            "admin_login_failed",
            username=username,
            client_ip=client_ip,
            detail={"failure_count": count, "retry_after_seconds": lock_seconds},
        )
        return lock_seconds

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        client_ip: str = "",
    ) -> Optional[Dict[str, Any]]:
        self.initialize_if_needed()
        normalized_username = username.strip()
        normalized_ip = client_ip.strip() or "unknown"
        with self._exclusive():
            attempts = self._active_attempts_unlocked()
            attempt_key = self._attempt_key(normalized_username, normalized_ip)
            retry_after = self._retry_after(attempts.get(attempt_key) or {})
            if retry_after:
                self._append_audit_unlocked(
                    "admin_login_blocked",
                    username=normalized_username,
                    client_ip=normalized_ip,
                    detail={"retry_after_seconds": retry_after},
                )
                raise AdminLoginThrottled(retry_after)
            if not self._verify_password_unlocked(normalized_username, password):
                retry_after = self._record_failure_unlocked(normalized_username, normalized_ip)
                if retry_after:
                    raise AdminLoginThrottled(retry_after)
                return None

            attempts.pop(attempt_key, None)
            self._write_json_unlocked(self.admin_attempts_path, {"attempts": attempts})
            admin = self._read_json_unlocked(self.admin_auth_path, {})
            expected_username = str(admin.get("username") or DEFAULT_ADMIN_USERNAME)
            token = secrets.token_urlsafe(36)
            session = {
                "token_hash": token_hash(token),
                "username": expected_username,
                "created_at": self._iso_now(),
                "expires_at": (self._now() + timedelta(hours=ADMIN_SESSION_HOURS)).isoformat(),
            }
            sessions = self._read_json_unlocked(self.admin_sessions_path, {"sessions": []})
            active = self._pruned_sessions(sessions.get("sessions") or [])
            active.append(session)
            self._write_json_unlocked(self.admin_sessions_path, {"sessions": active[-ADMIN_MAX_SESSIONS:]})
            self._append_audit_unlocked(
                "admin_login_succeeded",
                username=expected_username,
                client_ip=normalized_ip,
            )
            return {
                "token": token,
                "username": expected_username,
                "must_change_password": bool(admin.get("must_change_password", True)),
                "expires_at": session["expires_at"],
            }

    def _pruned_sessions(self, sessions: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        now = self._now()
        active: list[Dict[str, Any]] = []
        for session in sessions:
            try:
                expires_at = datetime.fromisoformat(str(session.get("expires_at") or ""))
            except ValueError:
                continue
            if expires_at > now and session.get("token_hash"):
                active.append(session)
        return active

    def session_status(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._exclusive():
            return self._session_status_unlocked(token)

    def _session_status_unlocked(self, token: str) -> Optional[Dict[str, Any]]:
        sessions_payload = self._read_json_unlocked(self.admin_sessions_path, {"sessions": []})
        sessions = self._pruned_sessions(sessions_payload.get("sessions") or [])
        if len(sessions) != len(sessions_payload.get("sessions") or []):
            self._write_json_unlocked(self.admin_sessions_path, {"sessions": sessions})
        current_hash = token_hash(token)
        for session in sessions:
            if hmac.compare_digest(str(session.get("token_hash") or ""), current_hash):
                return {
                    "username": session.get("username") or DEFAULT_ADMIN_USERNAME,
                    "created_at": session.get("created_at") or "",
                    "expires_at": session.get("expires_at") or "",
                }
        return None

    def logout(self, token: str) -> None:
        if not token:
            return
        with self._exclusive():
            sessions_payload = self._read_json_unlocked(self.admin_sessions_path, {"sessions": []})
            current_hash = token_hash(token)
            active = [
                session for session in self._pruned_sessions(sessions_payload.get("sessions") or [])
                if not hmac.compare_digest(str(session.get("token_hash") or ""), current_hash)
            ]
            self._write_json_unlocked(self.admin_sessions_path, {"sessions": active})
            self._append_audit_unlocked("admin_logout")

    def change_password(
        self,
        token: str,
        old_password: str,
        new_password: str,
        *,
        client_ip: str = "",
    ) -> bool:
        if len(new_password) < 10 or new_password == LEGACY_DEFAULT_ADMIN_PASSWORD:
            return False
        with self._exclusive():
            session = self._session_status_unlocked(token)
            if not session:
                return False
            username = str(session.get("username") or DEFAULT_ADMIN_USERNAME)
            if not self._verify_password_unlocked(username, old_password):
                self._append_audit_unlocked(
                    "admin_password_change_failed",
                    username=username,
                    client_ip=client_ip,
                )
                return False
            salt = secrets.token_hex(16)
            changed_at = self._iso_now()
            payload = {
                "username": username,
                "password_hash": password_hash(new_password, salt),
                "salt": salt,
                "must_change_password": False,
                "credential_kind": "user_defined",
                "password_changed_at": changed_at,
                "updated_at": changed_at,
            }
            self._write_json_unlocked(self.admin_auth_path, payload)
            self._write_json_unlocked(self.admin_sessions_path, {"sessions": []})
            self._write_json_unlocked(self.admin_attempts_path, {"attempts": {}})
            self.admin_credential_path.unlink(missing_ok=True)
            self._append_audit_unlocked(
                "admin_password_changed",
                username=username,
                client_ip=client_ip,
            )
            return True

    def read_setup_credential(self) -> str:
        with self._exclusive():
            if not self.admin_credential_path.exists():
                return ""
            return self.admin_credential_path.read_text(encoding="utf-8").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize GoHome edge box local identity and admin account.")
    parser.add_argument("command", nargs="?", default="init", choices=["init", "status", "reset-admin", "credential"])
    parser.add_argument("--username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--password", default=None, help="operator-supplied reset password; omitted generates a one-time credential")
    args = parser.parse_args()

    service = BoxInitService(settings)
    if args.command == "credential":
        credential = service.read_setup_credential()
        if not credential:
            raise SystemExit("No pending one-time admin credential")
        print(credential)
        return
    if args.command == "reset-admin":
        result = service.initialize(
            reset_admin=True,
            username=args.username,
            password=args.password,
            must_change_password=True,
        )
    elif args.command == "status":
        result = service.status()
    else:
        result = service.initialize(
            reset_admin=False,
            username=args.username,
            must_change_password=True,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command in {"init", "reset-admin"}:
        credential = service.read_setup_credential()
        if credential:
            print(f"One-time admin credential: {credential}")


if __name__ == "__main__":
    main()
