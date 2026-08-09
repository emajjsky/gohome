from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path
from typing import Any, Callable, Dict, Iterable
from urllib.parse import urlsplit, urlunsplit
import re
import socket
import subprocess


MAC_RE = re.compile(r"(?:lladdr|HWaddr)\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.IGNORECASE)


@dataclass(frozen=True)
class CameraEndpoint:
    host: str
    port: int
    path: str
    network_identity: str

    @property
    def stream_url(self) -> str:
        return urlunsplit(("rtsp", f"{self.host}:{self.port}", self.path, "", ""))


def normalize_network_identity(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", ":")


def parse_endpoint(stream_url: str) -> tuple[str, int, str] | None:
    try:
        parsed = urlsplit(str(stream_url or "").strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"rtsp", "rtsps"} or not parsed.hostname:
        return None
    port = int(parsed.port or 554)
    path = parsed.path or "/1/2"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.hostname, port, path


def replace_endpoint_host(stream_url: str, host: str) -> str:
    parsed = urlsplit(str(stream_url or "").strip())
    if not parsed.hostname:
        raise ValueError("stream URL has no host")
    port = parsed.port or 554
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/1/2", parsed.query, ""))


def local_subnet_hosts(local_ip: str) -> Iterable[str]:
    try:
        network = ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return ()
    return (str(host) for host in network.hosts() if str(host) != str(local_ip))


def network_identity_for_host(host: str, *, arp_path: Path = Path("/proc/net/arp")) -> str:
    try:
        result = subprocess.run(
            ["ip", "neigh", "show", host],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        match = MAC_RE.search(result.stdout or "")
        if match:
            return normalize_network_identity(match.group(1))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        for line in arp_path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 4 and fields[0] == host and fields[3] != "00:00:00:00:00:00":
                return normalize_network_identity(fields[3])
    except OSError:
        pass
    return ""


class CameraEndpointResolver:
    """Resolve a DHCP-moved RTSP endpoint without changing camera identity."""

    def __init__(
        self,
        *,
        local_ip_resolver: Callable[[], str],
        probe: Callable[[Dict[str, Any]], Any],
        match_score: Callable[[Dict[str, Any], Any], float] | None = None,
        port_timeout_seconds: float = 0.18,
        minimum_match_score: float = 20.0,
        minimum_match_margin: float = 8.0,
    ) -> None:
        self._local_ip_resolver = local_ip_resolver
        self._probe = probe
        self._match_score = match_score
        self._port_timeout_seconds = max(0.05, float(port_timeout_seconds))
        self._minimum_match_score = max(0.0, float(minimum_match_score))
        self._minimum_match_margin = max(0.0, float(minimum_match_margin))

    def observe(self, camera: Dict[str, Any]) -> CameraEndpoint | None:
        parsed = parse_endpoint(str(camera.get("stream_url") or ""))
        if parsed is None:
            return None
        host, port, path = parsed
        if not self._port_open(host, port):
            return None
        identity = network_identity_for_host(host)
        if not identity:
            return None
        return CameraEndpoint(host, port, path, identity)

    def resolve(
        self,
        camera: Dict[str, Any],
        *,
        network_identity: str = "",
        used_identities: set[str] | None = None,
    ) -> CameraEndpoint | None:
        parsed = parse_endpoint(str(camera.get("stream_url") or ""))
        if parsed is None:
            return None
        old_host, port, path = parsed
        expected_identity = normalize_network_identity(network_identity)
        used = {normalize_network_identity(item) for item in (used_identities or set()) if item}
        hosts = list(local_subnet_hosts(self._local_ip_resolver()))
        hosts.sort(key=lambda host: (host != old_host, host))
        candidates: list[tuple[CameraEndpoint, float]] = []
        for host in hosts:
            if not self._port_open(host, port):
                continue
            identity = network_identity_for_host(host)
            if not identity:
                continue
            if expected_identity and identity != expected_identity:
                continue
            if identity and identity in used and identity != expected_identity:
                continue
            candidate_url = replace_endpoint_host(str(camera["stream_url"]), host)
            candidate = dict(camera)
            candidate["stream_url"] = candidate_url
            try:
                probe_result = self._probe(candidate)
            except Exception:
                probe_result = None
            if probe_result is not None and probe_result is not False:
                endpoint = CameraEndpoint(host, port, path, identity)
                if expected_identity:
                    return endpoint
                score = (
                    float(self._match_score(camera, probe_result))
                    if self._match_score is not None
                    else 0.0
                )
                candidates.append((endpoint, score))
        if self._match_score is None:
            return candidates[0][0] if len(candidates) == 1 else None
        candidates.sort(key=lambda item: item[1], reverse=True)
        if not candidates or candidates[0][1] < self._minimum_match_score:
            return None
        runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
        if candidates[0][1] - runner_up < self._minimum_match_margin:
            return None
        return candidates[0][0]

    def _port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=self._port_timeout_seconds):
                return True
        except OSError:
            return False


class CalibrationSceneMatcher:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)

    def score(self, camera: Dict[str, Any], probe_result: Any) -> float:
        frame = probe_result.get("frame") if isinstance(probe_result, dict) else None
        camera_id = int(camera.get("id") or 0)
        if frame is None or camera_id <= 0:
            return 0.0
        try:
            import numpy as np  # type: ignore

            from .vision.privacy_scene_geometry import SceneGeometryVerifier
        except (ImportError, ModuleNotFoundError):
            return 0.0
        best = 0.0
        verifier = SceneGeometryVerifier()
        for path in self.storage_dir.glob(f"camera-{camera_id}-*.npz"):
            try:
                with np.load(path, allow_pickle=False) as payload:
                    background = payload["background"]
                assessment = verifier.assess(background, frame, excluded_mask=None)
            except (OSError, KeyError, ValueError, TypeError):
                continue
            good_matches = float(assessment.get("geometry_good_matches") or 0.0)
            inliers = float(assessment.get("geometry_inliers") or 0.0)
            inlier_ratio = float(assessment.get("geometry_inlier_ratio") or 0.0)
            grid_coverage = float(assessment.get("geometry_grid_coverage_ratio") or 0.0)
            if good_matches < 16.0 or inliers < 10.0 or inlier_ratio < 0.45:
                continue
            status_bonus = 20.0 if assessment.get("geometry_status") == "same_view" else 0.0
            score = (
                status_bonus
                + inliers
                + good_matches * 0.1
                + inlier_ratio * 10.0
                + grid_coverage * 5.0
            )
            best = max(best, score)
        return round(best, 4)
