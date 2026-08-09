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
        probe: Callable[[Dict[str, Any]], bool],
        port_timeout_seconds: float = 0.18,
    ) -> None:
        self._local_ip_resolver = local_ip_resolver
        self._probe = probe
        self._port_timeout_seconds = max(0.05, float(port_timeout_seconds))

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
        candidates: list[CameraEndpoint] = []
        for host in hosts:
            if not self._port_open(host, port):
                continue
            identity = network_identity_for_host(host)
            if expected_identity and identity != expected_identity:
                continue
            if identity and identity in used and identity != expected_identity:
                continue
            candidate_url = replace_endpoint_host(str(camera["stream_url"]), host)
            candidate = dict(camera)
            candidate["stream_url"] = candidate_url
            try:
                valid = bool(self._probe(candidate))
            except Exception:
                valid = False
            if valid:
                candidates.append(CameraEndpoint(host, port, path, identity))
                if expected_identity:
                    return candidates[0]
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=self._port_timeout_seconds):
                return True
        except OSError:
            return False
