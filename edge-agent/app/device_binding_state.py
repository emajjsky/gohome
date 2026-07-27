from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Dict
import json


class DeviceBindingState:
    """Persists the sanitized cloud ownership summary shown by the local admin UI."""

    ALLOWED_FIELDS = (
        "status",
        "family_name",
        "owner_account",
        "owner_display_name",
        "bound_at",
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def read(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return self.unbound()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return self.unbound()
        return self.sanitize(payload)

    def write(self, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        summary = self.sanitize(payload)
        if summary["status"] != "bound":
            return self.clear()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
        return summary

    def clear(self) -> Dict[str, Any]:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return self.unbound()

    @classmethod
    def sanitize(cls, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        status = "bound" if str(source.get("status") or "").lower() == "bound" else "unbound"
        if status != "bound":
            return cls.unbound()
        return {
            field: str(source.get(field) or "").strip()
            for field in cls.ALLOWED_FIELDS
        }

    @staticmethod
    def unbound() -> Dict[str, Any]:
        return {
            "status": "unbound",
            "family_name": "",
            "owner_account": "",
            "owner_display_name": "",
            "bound_at": "",
        }
