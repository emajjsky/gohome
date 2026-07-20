from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_config_authority import camera_config_authority


class FakeStorage:
    def __init__(self, family_ids: list[int]) -> None:
        self.family_ids = family_ids

    def list_device_bound_family_ids(self, _device_id: str) -> list[int]:
        return list(self.family_ids)


def main() -> None:
    cloud_settings = SimpleNamespace(
        config_sync_enabled=True,
        app_server_base_url="https://gohome.example",
    )
    cloud = camera_config_authority(cloud_settings, FakeStorage([2]), "edge-test")
    if cloud["mode"] != "cloud_managed" or cloud["local_mutation_allowed"]:
        raise SystemExit(f"bound cloud camera config is not authoritative: {cloud}")

    unbound = camera_config_authority(cloud_settings, FakeStorage([]), "edge-test")
    if unbound["mode"] != "local_setup" or not unbound["local_mutation_allowed"]:
        raise SystemExit(f"unbound setup must allow local camera setup: {unbound}")

    claimed = camera_config_authority(
        cloud_settings,
        FakeStorage([]),
        "edge-test",
        cloud_claimed=True,
    )
    if claimed["mode"] != "cloud_managed" or claimed["local_mutation_allowed"]:
        raise SystemExit(f"issued cloud token must make camera config authoritative: {claimed}")

    local_settings = SimpleNamespace(config_sync_enabled=False, app_server_base_url="")
    local = camera_config_authority(local_settings, FakeStorage([2]), "edge-test")
    if local["mode"] != "local_setup" or not local["local_mutation_allowed"]:
        raise SystemExit(f"local-only mode must allow local camera setup: {local}")

    print({"ok": True, "cloud": cloud, "unbound": unbound, "claimed": claimed, "local": local})


if __name__ == "__main__":
    main()
