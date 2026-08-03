from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.box_init_service import AdminLoginThrottled, BoxInitService, password_hash


class Settings:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_legacy_rotation(root: Path) -> None:
    service = BoxInitService(Settings(root / "legacy"))
    service.initialize()
    salt = "11" * 16
    legacy = {
        "username": "admin",
        "password_hash": password_hash("123456", salt),
        "salt": salt,
        "must_change_password": False,
        "password_changed_at": "",
        "updated_at": "legacy",
    }
    service.admin_auth_path.write_text(json.dumps(legacy), encoding="utf-8")

    service.initialize_if_needed()
    replacement = service.read_setup_credential()
    if len(replacement) < 16 or replacement == "123456":
        raise SystemExit("legacy default credential was not rotated to a unique one-time value")
    if service.authenticate("admin", "123456", client_ip="192.168.1.20") is not None:
        raise SystemExit("legacy universal password still authenticates after migration")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        clock = Clock()
        service = BoxInitService(Settings(root / "new-box"), clock=clock)
        service.initialize_if_needed()
        status = service.status()
        credential = service.read_setup_credential()

        if len(credential) < 16 or credential == "123456":
            raise SystemExit("new box did not receive a unique one-time credential")
        serialized_status = json.dumps(status, ensure_ascii=False)
        if credential in serialized_status or "password_hash" in serialized_status or "setup_credential" in serialized_status:
            raise SystemExit("public admin status leaks credential material or credential state")
        credential_mode = stat.S_IMODE(service.admin_credential_path.stat().st_mode)
        if credential_mode != 0o600:
            raise SystemExit(f"one-time credential permissions are not 0600: {oct(credential_mode)}")
        try:
            service.reset_admin_password(password="123456", must_change_password=False)
        except ValueError:
            pass
        else:
            raise SystemExit("operator reset still accepts the historical universal password")

        client_ip = "192.168.1.30"
        for _ in range(2):
            if service.authenticate("admin", "wrong", client_ip=client_ip) is not None:
                raise SystemExit("invalid password authenticated")
        try:
            service.authenticate("admin", "wrong", client_ip=client_ip)
        except AdminLoginThrottled as exc:
            if exc.retry_after_seconds != 1:
                raise SystemExit(f"unexpected initial lock duration: {exc.retry_after_seconds}")
        else:
            raise SystemExit("third consecutive failure did not trigger a bounded lock")

        try:
            service.authenticate("admin", credential, client_ip=client_ip)
        except AdminLoginThrottled:
            pass
        else:
            raise SystemExit("valid password bypassed an active lock")
        clock.advance(1)
        first_session = service.authenticate("admin", credential, client_ip=client_ip)
        if first_session is None:
            raise SystemExit("successful login did not recover after lock expiry")
        if not first_session["must_change_password"]:
            raise SystemExit("new box does not force the first password change")

        bounded_ip = "192.168.1.40"
        lock_durations: list[int] = []
        for _ in range(12):
            try:
                service.authenticate("admin", "wrong", client_ip=bounded_ip)
            except AdminLoginThrottled as exc:
                lock_durations.append(exc.retry_after_seconds)
                clock.advance(exc.retry_after_seconds)
        if not lock_durations or max(lock_durations) != 300:
            raise SystemExit(f"exponential lock is not capped at 300 seconds: {lock_durations}")

        def login(index: int) -> str:
            result = service.authenticate("admin", credential, client_ip=f"192.168.2.{index + 1}")
            if result is None:
                raise RuntimeError("concurrent login failed")
            return str(result["token"])

        with ThreadPoolExecutor(max_workers=8) as executor:
            tokens = list(executor.map(login, range(8)))
        sessions = load_json(service.admin_sessions_path).get("sessions") or []
        if len(sessions) != 9 or len(set(tokens)) != 8:
            raise SystemExit(f"concurrent session update lost data: {len(sessions)} sessions")

        audit_before = load_json(service.admin_audit_path).get("records") or []
        login_successes_before = sum(record.get("event") == "admin_login_succeeded" for record in audit_before)
        changed = service.change_password(
            str(first_session["token"]),
            credential,
            "new-admin-password-2026",
            client_ip=client_ip,
        )
        if not changed:
            raise SystemExit("valid password change failed")
        if service.admin_credential_path.exists():
            raise SystemExit("one-time credential survived successful password change")
        if load_json(service.admin_sessions_path).get("sessions") != []:
            raise SystemExit("password change did not revoke all sessions")

        audit_after = load_json(service.admin_audit_path).get("records") or []
        login_successes_after = sum(record.get("event") == "admin_login_succeeded" for record in audit_after)
        if login_successes_after != login_successes_before:
            raise SystemExit("password change created a hidden authentication session")
        if not any(record.get("event") == "admin_password_changed" for record in audit_after):
            raise SystemExit("password change was not written to the security audit")

        replacement_session = service.authenticate(
            "admin",
            "new-admin-password-2026",
            client_ip="192.168.1.31",
        )
        if replacement_session is None:
            raise SystemExit("new password does not authenticate")
        if service.status(str(replacement_session["token"]))["must_change_password"]:
            raise SystemExit("user-defined password remains marked as one-time")

        verify_legacy_rotation(root)

        login_html = (ROOT / "admin" / "login.html").read_text(encoding="utf-8")
        main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        init_script = (ROOT / "scripts" / "init-box.sh").read_text(encoding="utf-8")
        if "admin / 123456" in login_html or "--password 123456" in init_script:
            raise SystemExit("universal development credential remains in a production entry")
        asset_revision = "20260803-auth-4"
        if login_html.count(asset_revision) != 2:
            raise SystemExit("login HTML does not version both authentication assets")
        if f'ADMIN_AUTH_ASSET_REVISION = "{asset_revision}"' not in main_source:
            raise SystemExit("protected-page redirects do not use the current login revision")
        if 'ADMIN_AUTH_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"' not in main_source:
            raise SystemExit("authentication responses do not declare a no-store cache policy")

        print({
            "ok": True,
            "concurrent_sessions": 9,
            "lock_seconds": {"initial": 1, "maximum": 300},
            "audit_records": len(audit_after),
            "legacy_rotated": True,
        })


if __name__ == "__main__":
    main()
