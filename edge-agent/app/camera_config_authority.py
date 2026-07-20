from __future__ import annotations

from typing import Any, Dict


def camera_config_authority(
    settings: Any,
    storage: Any,
    device_id: str,
    *,
    cloud_claimed: bool = False,
) -> Dict[str, Any]:
    sync_enabled = bool(getattr(settings, "config_sync_enabled", False))
    cloud_configured = bool(str(getattr(settings, "app_server_base_url", "") or "").strip())
    family_ids = storage.list_device_bound_family_ids(str(device_id or "")) if device_id else []
    cloud_managed = sync_enabled and cloud_configured and (bool(family_ids) or bool(cloud_claimed))
    return {
        "mode": "cloud_managed" if cloud_managed else "local_setup",
        "local_mutation_allowed": not cloud_managed,
        "sync_enabled": sync_enabled,
        "cloud_configured": cloud_configured,
        "bound": bool(family_ids),
        "cloud_claimed": bool(cloud_claimed),
        "family_ids": [int(family_id) for family_id in family_ids],
    }
