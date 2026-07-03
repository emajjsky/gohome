from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict
from urllib.parse import urlparse

from .storage import Storage


class VideoDistributionService:
    def __init__(
        self,
        *,
        storage: Storage,
        settings: Any,
        current_device_identity_resolver: Callable[[], Dict[str, Any]],
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.current_device_identity = current_device_identity_resolver

    def normalize_base_url(self, value: str | None) -> str:
        return str(value or "").strip().rstrip("/")

    def local_base_url(self) -> str:
        identity = self.current_device_identity()
        lan_ip = str(identity.get("lan_ip") or "127.0.0.1").strip() or "127.0.0.1"
        api_port = int(identity.get("api_port") or self.settings.port)
        return f"http://{lan_ip}:{api_port}"

    def is_public_url(self, value: str | None) -> bool:
        raw = self.normalize_base_url(value)
        if not raw:
            return False
        host = (urlparse(raw).hostname or "").lower()
        if not host:
            return False
        if host in {"127.0.0.1", "localhost"}:
            return False
        if host.startswith("10.") or host.startswith("192.168."):
            return False
        if host.startswith("172."):
            parts = host.split(".")
            if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return False
        return True

    def current_node_id(self) -> str:
        identity = self.current_device_identity()
        return str(self.settings.video_service_node_id or identity.get("device_id") or "")

    def video_base_url(self) -> str:
        return (
            self.normalize_base_url(self.settings.video_service_public_base_url)
            or self.normalize_base_url(self.settings.public_base_url)
            or self.local_base_url()
        )

    def media_base_url(self) -> str:
        return (
            self.normalize_base_url(self.settings.media_public_base_url)
            or self.normalize_base_url(self.settings.public_base_url)
            or self.video_base_url()
        )

    def absolute_url(self, base_url: str, path: str) -> str:
        value = str(path or "").strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return value
        base = self.normalize_base_url(base_url)
        if not base:
            return value
        if value.startswith("/"):
            return f"{base}{value}"
        return f"{base}/{value}"

    def absolute_video_url(self, path: str) -> str:
        return self.absolute_url(self.video_base_url(), path)

    def absolute_media_url(self, path: str) -> str:
        return self.absolute_url(self.media_base_url(), path)

    def fallback_current_node(self) -> Dict[str, Any]:
        identity = self.current_device_identity()
        local_url = self.local_base_url()
        return {
            "id": None,
            "family_id": None,
            "node_id": self.current_node_id(),
            "device_id": str(identity.get("device_id") or ""),
            "device_name": str(identity.get("device_name") or ""),
            "node_name": str(identity.get("device_name") or ""),
            "role": str(self.settings.video_service_role or "origin"),
            "region": str(self.settings.video_service_region or "local"),
            "distribution": str(self.settings.video_distribution_name or "single-origin"),
            "health_status": "active",
            "priority": 100,
            "lan_url": local_url,
            "service_url": self.video_base_url(),
            "media_url": self.media_base_url(),
            "public_base_url": self.normalize_base_url(self.settings.public_base_url),
            "is_public_service_url": self.is_public_url(self.video_base_url()),
            "is_public_media_url": self.is_public_url(self.media_base_url()),
            "source": "settings",
            "capabilities": {},
            "metadata": {},
            "last_seen_at": None,
            "expires_at": None,
        }

    def normalize_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(node)
        fallback = self.fallback_current_node()
        service_url = self.normalize_base_url(data.get("service_url")) or fallback["service_url"]
        media_url = self.normalize_base_url(data.get("media_url")) or service_url or fallback["media_url"]
        public_base_url = self.normalize_base_url(data.get("public_base_url")) or self.normalize_base_url(self.settings.public_base_url)
        data["node_id"] = str(data.get("node_id") or fallback["node_id"])
        data["device_id"] = str(data.get("device_id") or "")
        data["device_name"] = str(data.get("device_name") or data.get("node_name") or "")
        data["node_name"] = str(data.get("node_name") or data.get("device_name") or data["node_id"])
        data["role"] = str(data.get("role") or "origin")
        data["region"] = str(data.get("region") or "local")
        data["distribution"] = str(self.settings.video_distribution_name or "single-origin")
        data["service_url"] = service_url
        data["media_url"] = media_url
        data["public_base_url"] = public_base_url
        data["lan_url"] = str(data.get("lan_url") or fallback["lan_url"])
        data["health_status"] = str(data.get("health_status") or "active")
        data["priority"] = int(data.get("priority") or 0)
        data["is_public_service_url"] = self.is_public_url(service_url)
        data["is_public_media_url"] = self.is_public_url(media_url)
        data["capabilities"] = dict(data.get("capabilities") or {})
        data["metadata"] = dict(data.get("metadata") or {})
        return data

    def current_node(self) -> Dict[str, Any]:
        return self.normalize_node(self.fallback_current_node())

    def register_node(
        self,
        *,
        family_id: int,
        node_id: str,
        device_id: str = "",
        node_name: str = "",
        role: str = "origin",
        region: str = "local",
        service_url: str = "",
        media_url: str = "",
        public_base_url: str = "",
        health_status: str = "active",
        priority: int = 100,
        heartbeat_expires_in_seconds: int = 300,
        capabilities: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(30, int(heartbeat_expires_in_seconds)))).isoformat()
        node = self.storage.upsert_video_service_node(
            family_id=family_id,
            node_id=node_id,
            device_id=device_id,
            node_name=node_name,
            role=role,
            region=region,
            service_url=service_url,
            media_url=media_url,
            public_base_url=public_base_url,
            health_status=health_status,
            priority=priority,
            capabilities=capabilities,
            metadata=metadata,
            expires_at=expires_at,
        )
        return self.normalize_node(node)

    def list_nodes(self, family_id: int, include_inactive: bool = False) -> list[Dict[str, Any]]:
        nodes = [self.normalize_node(item) for item in self.storage.list_video_service_nodes(family_id, include_inactive=include_inactive)]
        if not nodes and family_id in set(self.storage.list_device_bound_family_ids(str(self.current_device_identity().get("device_id") or ""))):
            return [self.current_node()]
        return nodes

    def _node_active(self, node: Dict[str, Any]) -> bool:
        if str(node.get("health_status") or "active") == "offline":
            return False
        expires_at = str(node.get("expires_at") or "")
        if not expires_at:
            return True
        try:
            return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
        except ValueError:
            return True

    def pick_node(
        self,
        *,
        family_id: int | None = None,
        preferred_region: str = "",
        require_public: bool = False,
        media: bool = False,
    ) -> Dict[str, Any]:
        fallback = self.current_node()
        if not family_id:
            return fallback
        nodes = self.list_nodes(int(family_id), include_inactive=True)
        candidates = [node for node in nodes if self._node_active(node)] or nodes
        if not candidates:
            return fallback
        region = str(preferred_region or "").strip().lower()

        def score(node: Dict[str, Any]) -> tuple[int, int, int, int]:
            node_region = str(node.get("region") or "").strip().lower()
            target_url = str(node.get("media_url" if media else "service_url") or "")
            is_public = self.is_public_url(target_url)
            exact_region = 1 if region and node_region == region else 0
            role_rank = {"relay": 3, "edge": 2, "origin": 1}.get(str(node.get("role") or ""), 0)
            public_rank = 1 if (not require_public or is_public) else 0
            return (public_rank, exact_region, int(node.get("priority") or 0), role_rank)

        selected = sorted(candidates, key=score, reverse=True)[0]
        if require_public:
            target_url = str(selected.get("media_url" if media else "service_url") or "")
            if not self.is_public_url(target_url):
                return fallback
        return selected

    def absolute_video_url_for_node(self, path: str, node: Dict[str, Any]) -> str:
        return self.absolute_url(str(node.get("service_url") or ""), path)

    def absolute_media_url_for_node(self, path: str, node: Dict[str, Any]) -> str:
        return self.absolute_url(str(node.get("media_url") or ""), path)

    def scheduled_service_info(
        self,
        *,
        family_id: int | None = None,
        preferred_region: str = "",
        require_public: bool = False,
        media: bool = False,
    ) -> Dict[str, Any]:
        node = self.pick_node(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=require_public,
            media=media,
        )
        return {
            "distribution": str(self.settings.video_distribution_name or "single-origin"),
            "service": node,
            "selection": {
                "family_id": family_id,
                "preferred_region": preferred_region,
                "require_public": require_public,
                "media": media,
                "selected_node_id": node.get("node_id"),
            },
        }

    def service_info(self) -> Dict[str, Any]:
        return self.scheduled_service_info()
