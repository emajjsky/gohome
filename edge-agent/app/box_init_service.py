from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket

from .settings import settings


ADMIN_SESSION_COOKIE = "gohome_admin_session"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"


def development_must_change_password() -> bool:
    value = os.environ.get("GOHOME_ADMIN_MUST_CHANGE_PASSWORD", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 180_000)
    return derived.hex()


class BoxInitService:
    def __init__(self, app_settings: Any) -> None:
        self.settings = app_settings
        self.state_path = Path(self.settings.data_dir) / "box_state.json"
        self.admin_auth_path = Path(self.settings.data_dir) / "admin_auth.json"
        self.admin_sessions_path = Path(self.settings.data_dir) / "admin_sessions.json"
        self.init_marker_path = Path(self.settings.data_dir) / ".box_initialized"

    def _read_json(self, path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return dict(fallback)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else dict(fallback)
        except (OSError, json.JSONDecodeError):
            return dict(fallback)

    def _write_json(self, path: Path, payload: Dict[str, Any], *, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_path, path)
        try:
            path.chmod(mode)
        except OSError:
            pass

    def _device_id_path(self) -> Path:
        return Path(self.settings.data_dir) / "device_id.txt"

    def ensure_device_id(self) -> str:
        path = self._device_id_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        device_id = f"edge-{secrets.token_hex(8)}"
        path.write_text(device_id, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return device_id

    def reset_admin_password(
        self,
        *,
        username: str = DEFAULT_ADMIN_USERNAME,
        password: str = DEFAULT_ADMIN_PASSWORD,
        must_change_password: bool = True,
    ) -> Dict[str, Any]:
        salt = secrets.token_hex(16)
        payload = {
            "username": username,
            "password_hash": password_hash(password, salt),
            "salt": salt,
            "must_change_password": must_change_password,
            "password_changed_at": "",
            "updated_at": iso_now(),
        }
        self._write_json(self.admin_auth_path, payload)
        self._write_json(self.admin_sessions_path, {"sessions": []})
        return payload

    def initialize(
        self,
        *,
        reset_admin: bool = False,
        username: str = DEFAULT_ADMIN_USERNAME,
        password: str = DEFAULT_ADMIN_PASSWORD,
        must_change_password: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if must_change_password is None:
            must_change_password = development_must_change_password()
        self.settings.ensure_dirs()
        device_id = self.ensure_device_id()
        state = self._read_json(self.state_path, {})
        now = iso_now()
        if not state.get("initialized"):
            state = {
                "initialized": True,
                "initialized_at": now,
                "device_id": device_id,
                "device_name": socket.gethostname(),
                "mdns_name": "gohome.local",
                "admin_username": username,
                "admin_default_password_set": True,
                "setup_version": 1,
            }
        else:
            state.update({
                "initialized": True,
                "device_id": state.get("device_id") or device_id,
                "device_name": socket.gethostname(),
                "mdns_name": state.get("mdns_name") or "gohome.local",
                "admin_username": state.get("admin_username") or username,
                "setup_version": state.get("setup_version") or 1,
            })
        state["updated_at"] = now
        self._write_json(self.state_path, state)
        self.init_marker_path.write_text(now, encoding="utf-8")

        if reset_admin or not self.admin_auth_path.exists():
            self.reset_admin_password(
                username=username,
                password=password,
                must_change_password=must_change_password,
            )

        return self.status()

    def initialize_if_needed(self) -> Dict[str, Any]:
        return self.initialize(reset_admin=False)

    def _admin_auth(self) -> Dict[str, Any]:
        self.initialize_if_needed()
        return self._read_json(self.admin_auth_path, {})

    def status(self, token: str = "") -> Dict[str, Any]:
        state = self._read_json(self.state_path, {})
        admin = self._read_json(self.admin_auth_path, {})
        session = self.session_status(token) if token else None
        return {
            "initialized": bool(state.get("initialized")),
            "device_id": state.get("device_id") or self.ensure_device_id(),
            "device_name": socket.gethostname(),
            "mdns_name": state.get("mdns_name") or "gohome.local",
            "admin_username": admin.get("username") or DEFAULT_ADMIN_USERNAME,
            "default_username": DEFAULT_ADMIN_USERNAME,
            "development_default_password_enabled": True,
            "must_change_password": bool(admin.get("must_change_password", True)),
            "authenticated": bool(session),
            "session": session or None,
            "initialized_at": state.get("initialized_at") or "",
            "updated_at": state.get("updated_at") or "",
        }

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        admin = self._admin_auth()
        expected_username = str(admin.get("username") or DEFAULT_ADMIN_USERNAME)
        salt = str(admin.get("salt") or "")
        stored_hash = str(admin.get("password_hash") or "")
        if username != expected_username or not salt or not stored_hash:
            return None
        actual_hash = password_hash(password, salt)
        if not hmac.compare_digest(actual_hash, stored_hash):
            return None
        token = secrets.token_urlsafe(36)
        session = {
            "token_hash": token_hash(token),
            "username": expected_username,
            "created_at": iso_now(),
            "expires_at": (utc_now() + timedelta(hours=12)).isoformat(),
        }
        sessions = self._read_json(self.admin_sessions_path, {"sessions": []})
        active = self._pruned_sessions(sessions.get("sessions") or [])
        active.append(session)
        self._write_json(self.admin_sessions_path, {"sessions": active})
        return {
            "token": token,
            "username": expected_username,
            "must_change_password": bool(admin.get("must_change_password", True)),
            "expires_at": session["expires_at"],
        }

    def _pruned_sessions(self, sessions: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        now = utc_now()
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
        sessions_payload = self._read_json(self.admin_sessions_path, {"sessions": []})
        sessions = self._pruned_sessions(sessions_payload.get("sessions") or [])
        if len(sessions) != len(sessions_payload.get("sessions") or []):
            self._write_json(self.admin_sessions_path, {"sessions": sessions})
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
        sessions_payload = self._read_json(self.admin_sessions_path, {"sessions": []})
        current_hash = token_hash(token)
        active = [
            session for session in self._pruned_sessions(sessions_payload.get("sessions") or [])
            if not hmac.compare_digest(str(session.get("token_hash") or ""), current_hash)
        ]
        self._write_json(self.admin_sessions_path, {"sessions": active})

    def change_password(self, token: str, old_password: str, new_password: str) -> bool:
        session = self.session_status(token)
        if not session:
            return False
        username = str(session.get("username") or DEFAULT_ADMIN_USERNAME)
        if not self.authenticate(username, old_password):
            return False
        salt = secrets.token_hex(16)
        payload = {
            "username": username,
            "password_hash": password_hash(new_password, salt),
            "salt": salt,
            "must_change_password": False,
            "password_changed_at": iso_now(),
            "updated_at": iso_now(),
        }
        self._write_json(self.admin_auth_path, payload)
        self._write_json(self.admin_sessions_path, {"sessions": []})
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize GoHome edge box local identity and admin account.")
    parser.add_argument("command", nargs="?", default="init", choices=["init", "status", "reset-admin"])
    parser.add_argument("--username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--password", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument(
        "--force-password-change",
        dest="must_change_password",
        action="store_true",
        default=None,
        help="require the admin password to be changed after first login",
    )
    parser.add_argument(
        "--no-force-password-change",
        dest="must_change_password",
        action="store_false",
        help="allow the initial admin password to be used directly in development",
    )
    args = parser.parse_args()

    service = BoxInitService(settings)
    if args.command == "reset-admin":
        result = service.initialize(
            reset_admin=True,
            username=args.username,
            password=args.password,
            must_change_password=args.must_change_password,
        )
    elif args.command == "status":
        service.initialize_if_needed()
        result = service.status()
    else:
        result = service.initialize(
            reset_admin=False,
            username=args.username,
            password=args.password,
            must_change_password=args.must_change_password,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
