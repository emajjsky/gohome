from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from .video_distribution_service import VideoDistributionService


class PublicPilotService:
    def __init__(self, *, settings: Any, distribution: VideoDistributionService) -> None:
        self.settings = settings
        self.distribution = distribution

    def public_web_base_url(self, *, family_id: int | None = None, preferred_region: str = "") -> str:
        explicit = self.distribution.normalize_base_url(self.settings.public_base_url)
        if self.distribution.is_public_url(explicit):
            return explicit
        service_info = self.distribution.scheduled_service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=True,
            media=False,
        )
        selected_service_url = self.distribution.normalize_base_url(service_info.get("service", {}).get("service_url"))
        if self.distribution.is_public_url(selected_service_url):
            return selected_service_url
        fallback_video = self.distribution.normalize_base_url(self.distribution.video_base_url())
        if self.distribution.is_public_url(fallback_video):
            return fallback_video
        return explicit

    def public_web_ready(self, *, family_id: int | None = None, preferred_region: str = "") -> bool:
        return self.distribution.is_public_url(
            self.public_web_base_url(family_id=family_id, preferred_region=preferred_region)
        )

    def notification_channel_status(self) -> Dict[str, Any]:
        channel = str(self.settings.notify_channel or "off").strip().lower() or "off"
        recipient = ""
        configured = False
        if channel == "webhook":
            recipient = str(self.settings.generic_webhook_url or "").strip()
            configured = bool(recipient)
        elif channel == "feishu":
            recipient = str(self.settings.feishu_webhook or "").strip()
            configured = bool(recipient)
        elif channel == "bark":
            recipient = str(self.settings.bark_url or "").strip()
            configured = bool(recipient)
        elif channel == "telegram":
            recipient = str(self.settings.telegram_chat_id or "").strip()
            configured = bool(str(self.settings.telegram_bot_token or "").strip() and recipient)
        return {
            "channel": channel,
            "recipient": recipient,
            "configured": configured,
            "supports_links": channel in {"webhook", "feishu", "bark", "telegram"},
        }

    def ui_url(
        self,
        page: str,
        params: Dict[str, Any] | None = None,
        *,
        family_id: int | None = None,
        preferred_region: str = "",
    ) -> str:
        base = self.public_web_base_url(family_id=family_id, preferred_region=preferred_region)
        if not base:
            return ""
        page_name = str(page or "").strip().lstrip("/")
        path = f"/ui/{page_name}"
        query = urlencode(
            [(str(key), str(value)) for key, value in dict(params or {}).items() if value not in {None, ""}],
            doseq=True,
        )
        return f"{base}{path}{'?' + query if query else ''}"

    def app_shell_url(self, next_path: str = "", *, family_id: int | None = None, preferred_region: str = "") -> str:
        params: Dict[str, Any] = {"app": 1}
        clean_next = str(next_path or "").strip()
        if clean_next:
            params["next"] = clean_next
        return self.ui_url("app-shell.html", params, family_id=family_id, preferred_region=preferred_region)

    def public_links(
        self,
        *,
        family_id: int | None = None,
        camera_id: int | None = None,
        event_id: int | None = None,
        preferred_region: str = "",
    ) -> Dict[str, Any]:
        next_watch = "watch.html"
        if camera_id:
            next_watch = f"watch.html?cameraId={int(camera_id)}"
        next_event = f"event_detail.html?eventId={int(event_id)}" if event_id else ""
        return {
            "public_base_url": self.public_web_base_url(family_id=family_id, preferred_region=preferred_region),
            "app_shell_url": self.app_shell_url(family_id=family_id, preferred_region=preferred_region),
            "watch_url": self.app_shell_url(next_watch, family_id=family_id, preferred_region=preferred_region),
            "events_url": self.app_shell_url("events.html", family_id=family_id, preferred_region=preferred_region),
            "event_url": self.app_shell_url(next_event, family_id=family_id, preferred_region=preferred_region) if next_event else "",
            "preferred_region": str(preferred_region or ""),
            "family_id": int(family_id) if family_id else None,
        }

    def enrich_notification_extra(
        self,
        *,
        family_id: int | None = None,
        extra: Dict[str, Any] | None = None,
        event_id: int | None = None,
        preferred_region: str = "",
    ) -> Dict[str, Any]:
        payload = dict(extra or {})
        camera_id = payload.get("camera_id")
        links = self.public_links(
            family_id=family_id,
            camera_id=int(camera_id) if camera_id else None,
            event_id=event_id,
            preferred_region=preferred_region,
        )
        payload["public_links"] = links
        payload["open_url"] = links.get("event_url") or links.get("watch_url") or links.get("app_shell_url")
        if links.get("event_url"):
            payload["event_url"] = links["event_url"]
        if links.get("watch_url"):
            payload["watch_url"] = links["watch_url"]
        if links.get("events_url"):
            payload["events_url"] = links["events_url"]
        if links.get("app_shell_url"):
            payload["app_shell_url"] = links["app_shell_url"]
        return payload

    def status(self, *, family_id: int | None = None, preferred_region: str = "") -> Dict[str, Any]:
        notification = self.notification_channel_status()
        video = self.distribution.scheduled_service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=True,
            media=False,
        )
        media = self.distribution.scheduled_service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=True,
            media=True,
        )
        public_web_ready = self.public_web_ready(family_id=family_id, preferred_region=preferred_region)
        video_ready = bool(video.get("service", {}).get("is_public_service_url"))
        media_ready = bool(media.get("service", {}).get("is_public_media_url"))
        checks = [
            {
                "key": "public_web",
                "ok": public_web_ready,
                "message": "public web base url is ready" if public_web_ready else "no public web base url or public service url available",
            },
            {
                "key": "public_video",
                "ok": video_ready,
                "message": "public video node is ready" if video_ready else "no public video service selected",
            },
            {
                "key": "public_media",
                "ok": media_ready,
                "message": "public media node is ready" if media_ready else "no public media service selected",
            },
            {
                "key": "notification_channel",
                "ok": bool(notification.get("configured")),
                "message": "notification channel is configured" if notification.get("configured") else "notification channel is missing or off",
            },
        ]
        return {
            "ready": all(bool(item["ok"]) for item in checks),
            "family_id": int(family_id) if family_id else None,
            "preferred_region": str(preferred_region or ""),
            "public_web_base_url": self.public_web_base_url(family_id=family_id, preferred_region=preferred_region),
            "public_web_ready": public_web_ready,
            "pages": self.public_links(family_id=family_id, preferred_region=preferred_region),
            "video_distribution": video,
            "media_distribution": media,
            "notification": notification,
            "checks": checks,
        }
