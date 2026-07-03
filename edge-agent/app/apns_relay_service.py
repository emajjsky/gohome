from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import base64
import json
import shutil
import subprocess
import time


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class APNSRelayService:
    def __init__(self, *, settings: Any) -> None:
        self.settings = settings
        self._cached_bearer = ""
        self._cached_bearer_at = 0

    @property
    def auth_key_path(self) -> Path | None:
        raw = str(self.settings.apns_auth_key_path or "").strip()
        return Path(raw) if raw else None

    def configured(self) -> bool:
        key_path = self.auth_key_path
        return bool(
            key_path
            and key_path.exists()
            and str(self.settings.apns_key_id or "").strip()
            and str(self.settings.apns_team_id or "").strip()
            and str(self.settings.apns_topic or "").strip()
        )

    def status(self) -> Dict[str, Any]:
        key_path = self.auth_key_path
        return {
            "provider": "apns",
            "configured": self.configured(),
            "env_files": list(getattr(self.settings, "env_files", []) or []),
            "auth_key_path": str(key_path) if key_path else "",
            "auth_key_exists": bool(key_path and key_path.exists()),
            "key_id": str(self.settings.apns_key_id or ""),
            "team_id": str(self.settings.apns_team_id or ""),
            "topic": str(self.settings.apns_topic or ""),
            "default_environment": str(self.settings.apns_default_environment or "production"),
            "request_timeout_seconds": float(self.settings.apns_request_timeout_seconds or 8),
            "curl_available": bool(shutil.which("curl")),
            "openssl_available": bool(shutil.which("openssl")),
        }

    def verify_internal_secret(self, authorization: str = "") -> bool:
        secret = str(self.settings.app_push_relay_secret or "").strip()
        if not secret:
            return False
        value = str(authorization or "").strip()
        return value == f"Bearer {secret}" or value == secret

    def _bearer_token(self) -> str:
        now = int(time.time())
        if self._cached_bearer and (now - self._cached_bearer_at) < 3000:
            return self._cached_bearer
        key_path = self.auth_key_path
        if key_path is None or not key_path.exists():
            raise RuntimeError("APNs auth key file is missing")
        header = {"alg": "ES256", "kid": str(self.settings.apns_key_id or "").strip()}
        payload = {"iss": str(self.settings.apns_team_id or "").strip(), "iat": now}
        if not header["kid"] or not payload["iss"]:
            raise RuntimeError("APNs key id or team id is missing")
        header_b64 = _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
            input=signing_input,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or b"openssl sign failed").decode("utf-8", errors="ignore").strip())
        signature_b64 = _base64url(result.stdout)
        self._cached_bearer = f"{header_b64}.{payload_b64}.{signature_b64}"
        self._cached_bearer_at = now
        return self._cached_bearer

    def _apns_host(self, environment: str) -> str:
        return "api.sandbox.push.apple.com" if str(environment or "").strip().lower() == "sandbox" else "api.push.apple.com"

    def _apns_payload(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        targets = dict(notification.get("targets") or {})
        web_targets = dict(targets.get("web") or {})
        return {
            "aps": {
                "alert": {
                    "title": str(notification.get("title") or "").strip(),
                    "body": str(notification.get("body") or "").strip(),
                },
                "sound": "default",
            },
            "gohome": {
                "family_id": notification.get("family_id"),
                "event_id": notification.get("event_id"),
                "camera_id": notification.get("camera_id"),
                "preferred_region": notification.get("preferred_region"),
                "open_deep_link": targets.get("open_deep_link") or "",
                "event_deep_link": targets.get("event_deep_link") or "",
                "watch_deep_link": targets.get("watch_deep_link") or "",
                "app_shell_deep_link": targets.get("app_shell_deep_link") or "",
                "open_url": web_targets.get("event_url") or web_targets.get("watch_url") or web_targets.get("app_shell_url") or "",
                "extra": dict(notification.get("extra") or {}),
            },
        }

    def _send_single(self, *, push_token: str, environment: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        bearer = self._bearer_token()
        host = self._apns_host(environment or self.settings.apns_default_environment)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("curl is not available")
        result = subprocess.run(
            [
                curl,
                "--http2",
                "-sS",
                "-X",
                "POST",
                "-o",
                "-",
                "-w",
                "\n%{http_code}",
                f"https://{host}/3/device/{push_token}",
                "-H",
                f"authorization: bearer {bearer}",
                "-H",
                f"apns-topic: {str(self.settings.apns_topic or '').strip()}",
                "-H",
                "apns-push-type: alert",
                "-H",
                "apns-priority: 10",
                "-H",
                "content-type: application/json",
                "--max-time",
                str(float(self.settings.apns_request_timeout_seconds or 8)),
                "-d",
                body,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "").rstrip()
        body_text = output
        http_code = 0
        if "\n" in output:
            body_text, _, code_text = output.rpartition("\n")
            try:
                http_code = int(code_text.strip() or "0")
            except ValueError:
                http_code = 0
        sent = result.returncode == 0 and 200 <= http_code < 300
        return {
            "sent": sent,
            "host": host,
            "status": http_code,
            "response_body": body_text[:500],
            "stderr": str(result.stderr or "").strip()[:500],
        }

    def deliver(self, relay_payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured():
            return {"sent": False, "provider": "apns", "reason": "apns relay is not configured"}
        tokens = [dict(item) for item in list(relay_payload.get("tokens") or []) if str(dict(item).get("provider") or "apns") == "apns"]
        if not tokens:
            return {"sent": False, "provider": "apns", "reason": "no apns tokens"}
        notification = dict(relay_payload.get("notification") or {})
        payload = self._apns_payload(notification)
        deliveries: list[Dict[str, Any]] = []
        sent_count = 0
        for token in tokens:
            try:
                result = self._send_single(
                    push_token=str(token.get("push_token") or "").strip(),
                    environment=str(token.get("environment") or self.settings.apns_default_environment),
                    payload=payload,
                )
            except Exception as exc:
                result = {"sent": False, "status": 0, "response_body": "", "stderr": str(exc), "host": ""}
            if result.get("sent"):
                sent_count += 1
            deliveries.append(
                {
                    "app_install_id": str(token.get("app_install_id") or ""),
                    "environment": str(token.get("environment") or ""),
                    "token_prefix": str(token.get("push_token") or "")[:8],
                    **result,
                }
            )
        failed_count = len(deliveries) - sent_count
        return {
            "sent": sent_count > 0,
            "provider": "apns",
            "token_count": len(deliveries),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "deliveries": deliveries,
        }
