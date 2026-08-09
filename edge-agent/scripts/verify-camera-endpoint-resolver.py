#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_endpoint_resolver import CameraEndpointResolver, replace_endpoint_host


class DeterministicResolver(CameraEndpointResolver):
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        super().__init__(
            local_ip_resolver=lambda: "10.0.0.12",
            probe=lambda camera: {"score": scores[urlsplit(camera["stream_url"]).hostname or ""]},
            match_score=lambda _camera, result: float(result["score"]),
        )

    def _discover_hosts(self, _port: int) -> list[tuple[str, str]]:
        return [
            ("10.0.0.41", "00:11:22:33:44:41"),
            ("10.0.0.42", "00:11:22:33:44:42"),
        ]


class CachedDiscoveryResolver(CameraEndpointResolver):
    def __init__(self) -> None:
        self.inspections = 0
        self.inspection_lock = Lock()
        super().__init__(
            local_ip_resolver=lambda: "10.0.0.12",
            probe=lambda _camera: True,
            discovery_cache_seconds=60.0,
        )

    def _inspect_host(self, host: str, _port: int) -> tuple[str, str] | None:
        with self.inspection_lock:
            self.inspections += 1
        if host == "10.0.0.41":
            return host, "00:11:22:33:44:41"
        return None


def main() -> None:
    camera = {
        "id": 31,
        "stream_url": "rtsp://viewer:secret@10.0.0.11:554/1/2",
        "enabled": True,
    }
    unique = DeterministicResolver({"10.0.0.41": 52.0, "10.0.0.42": 27.0})
    resolved = unique.resolve(camera)
    assert resolved is not None and resolved.host == "10.0.0.41"

    ambiguous = DeterministicResolver({"10.0.0.41": 52.0, "10.0.0.42": 47.0})
    assert ambiguous.resolve(camera) is None

    exact_identity = DeterministicResolver({"10.0.0.41": 1.0, "10.0.0.42": 1.0})
    resolved_by_identity = exact_identity.resolve(
        camera,
        network_identity="00:11:22:33:44:42",
    )
    assert resolved_by_identity is not None and resolved_by_identity.host == "10.0.0.42"

    excluded = unique.resolve(camera, used_identities={"00:11:22:33:44:41"})
    assert excluded is not None and excluded.host == "10.0.0.42"

    replaced = replace_endpoint_host(camera["stream_url"], "10.0.0.41")
    assert replaced == "rtsp://viewer:secret@10.0.0.41:554/1/2"

    cached = CachedDiscoveryResolver()
    assert cached._discover_hosts(554) == [("10.0.0.41", "00:11:22:33:44:41")]
    first_scan_inspections = cached.inspections
    assert first_scan_inspections == 253
    assert cached._discover_hosts(554) == [("10.0.0.41", "00:11:22:33:44:41")]
    assert cached.inspections == first_scan_inspections

    print({
        "ok": True,
        "unique_scene_match": True,
        "ambiguous_scene_rejected": True,
        "stable_identity_match": True,
        "used_identity_excluded": True,
        "credentials_preserved": True,
        "subnet_scan_reused": True,
    })


if __name__ == "__main__":
    main()
