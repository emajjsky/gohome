from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib import request
from urllib.parse import urlencode
import json

from .public_pilot_service import PublicPilotService
from .storage import Storage


class AppPushService:
    def __init__(self, *, storage: Storage, settings: Any, public_pilot: PublicPilotService, apns_relay: Any | None = None) -> None:
        self.storage = storage
        self.settings = settings
        self.public_pilot = public_pilot
        self.apns_relay = apns_relay

    def provider_status(self) -> Dict[str, Any]:
        provider = str(self.settings.app_push_provider or "off").strip().lower() or "off"
        relay_url = str(self.settings.app_push_relay_url or "").strip()
        status = {
            "provider": provider,
            "configured": provider == "relay" and bool(relay_url),
            "relay_url": relay_url,
            "deep_link_scheme": str(self.settings.app_deep_link_scheme or "gohome"),
        }
        if provider == "apns" and self.apns_relay is not None:
            apns_status = dict(self.apns_relay.status())
            status.update(apns_status)
            status["provider"] = "apns"
            status["deep_link_scheme"] = str(self.settings.app_deep_link_scheme or "gohome")
        return status

    def deep_link(self, next_path: str = "") -> str:
        scheme = str(self.settings.app_deep_link_scheme or "gohome").strip() or "gohome"
        params = {"app": "1"}
        if next_path:
            params["next"] = str(next_path)
        return f"{scheme}://open?{urlencode(params)}"

    def open_targets(
        self,
        *,
        family_id: int,
        event_id: Optional[int] = None,
        camera_id: Optional[int] = None,
        preferred_region: str = "",
    ) -> Dict[str, Any]:
        next_watch = "watch.html"
        if camera_id:
            next_watch = f"watch.html?cameraId={int(camera_id)}"
        next_event = f"event_detail.html?eventId={int(event_id)}" if event_id else ""
        web_links = self.public_pilot.public_links(
            family_id=family_id,
            event_id=event_id,
            camera_id=camera_id,
            preferred_region=preferred_region,
        )
        return {
            "app_shell_deep_link": self.deep_link(),
            "watch_deep_link": self.deep_link(next_watch),
            "event_deep_link": self.deep_link(next_event) if next_event else "",
            "open_deep_link": self.deep_link(next_event or next_watch),
            "web": web_links,
        }

    def register_token(
        self,
        *,
        family_id: int,
        user_id: int,
        app_install_id: str,
        platform: str,
        provider: str,
        push_token: str,
        device_name: str = "",
        app_version: str = "",
        environment: str = "production",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.storage.upsert_app_push_token(
            family_id=family_id,
            user_id=user_id,
            app_install_id=app_install_id,
            platform=platform,
            provider=provider,
            push_token=push_token,
            device_name=device_name,
            app_version=app_version,
            environment=environment,
            metadata=metadata,
        )

    def list_tokens(self, *, user_id: int, family_id: Optional[int] = None) -> list[Dict[str, Any]]:
        return self.storage.list_user_app_push_tokens(user_id=user_id, family_id=family_id)

    def revoke_token(self, *, user_id: int, app_install_id: str) -> Optional[Dict[str, Any]]:
        return self.storage.deactivate_app_push_token(user_id=user_id, app_install_id=app_install_id)

    def _relay_send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        relay_url = str(self.settings.app_push_relay_url or "").strip()
        if not relay_url:
            return {"sent": False, "reason": "missing app push relay url", "provider": "relay"}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = str(self.settings.app_push_relay_secret or "").strip()
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        req = request.Request(relay_url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=8) as response:
                return {
                    "sent": 200 <= response.status < 300,
                    "provider": "relay",
                    "status": response.status,
                    "body": response.read().decode("utf-8", errors="ignore")[:500],
                }
        except Exception as exc:
            return {"sent": False, "provider": "relay", "reason": str(exc)}

    def send_to_family(
        self,
        *,
        family_id: int,
        title: str,
        body: str,
        event_id: Optional[int] = None,
        camera_id: Optional[int] = None,
        preferred_region: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        provider_status = self.provider_status()
        tokens = self.storage.list_family_app_push_tokens(family_id, include_secret=True)
        targets = self.open_targets(
            family_id=family_id,
            event_id=event_id,
            camera_id=camera_id,
            preferred_region=preferred_region,
        )
        payload = {
            "title": str(title or "").strip(),
            "body": str(body or "").strip(),
            "family_id": int(family_id),
            "event_id": int(event_id) if event_id else None,
            "camera_id": int(camera_id) if camera_id else None,
            "preferred_region": str(preferred_region or ""),
            "targets": targets,
            "extra": dict(extra or {}),
        }

        if not tokens:
            return self.storage.create_notification_delivery(
                family_id=family_id,
                event_id=event_id,
                channel="app_push",
                title=title,
                body=body,
                recipient="0 app tokens",
                status="skipped",
                response={
                    "sent": False,
                    "provider": provider_status["provider"],
                    "reason": "no active app push tokens",
                    "token_count": 0,
                    "targets": targets,
                },
                delivered_at=None,
            )

        if provider_status["provider"] == "off":
            return self.storage.create_notification_delivery(
                family_id=family_id,
                event_id=event_id,
                channel="app_push",
                title=title,
                body=body,
                recipient=f"{len(tokens)} app tokens",
                status="skipped",
                response={
                    "sent": False,
                    "provider": "off",
                    "reason": "app push provider is off",
                    "token_count": len(tokens),
                    "targets": targets,
                },
                delivered_at=None,
            )

        relay_payload = {
            "tokens": [
                {
                    "app_install_id": token["app_install_id"],
                    "provider": token["provider"],
                    "platform": token["platform"],
                    "environment": token["environment"],
                    "push_token": token["push_token"],
                }
                for token in tokens
            ],
            "notification": payload,
        }
        if provider_status["provider"] == "relay":
            result = self._relay_send(relay_payload)
        elif provider_status["provider"] == "apns" and self.apns_relay is not None:
            result = self.apns_relay.deliver(relay_payload)
        else:
            result = {
                "sent": False,
                "provider": provider_status["provider"],
                "reason": "unsupported app push provider",
            }
        status = "sent" if result.get("sent") else "failed"
        delivered_at = datetime.now(timezone.utc).isoformat() if status == "sent" else None
        return self.storage.create_notification_delivery(
            family_id=family_id,
            event_id=event_id,
            channel="app_push",
            title=title,
            body=body,
            recipient=f"{len(tokens)} app tokens",
            status=status,
            response={
                **result,
                "token_count": len(tokens),
                "token_targets": [
                    {
                        "app_install_id": token["app_install_id"],
                        "platform": token["platform"],
                        "provider": token["provider"],
                        "environment": token["environment"],
                        "token_prefix": token["token_prefix"],
                    }
                    for token in tokens
                ],
                "targets": targets,
            },
            delivered_at=delivered_at,
        )
