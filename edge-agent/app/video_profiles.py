from __future__ import annotations

from typing import Any, Dict


DEFAULT_STREAM_PROFILE = "default"


# Data-only profile definitions for video distribution/transcode presets.
STREAM_DISTRIBUTION_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "label": "default",
        "distribution": "mjpeg",
        "fps": 5,
        "width": 960,
        "height": 540,
        "quality": 60,
        "drop": 4,
    },
    "detail": {
        "label": "detail",
        "distribution": "mjpeg",
        "fps": 5,
        "width": 960,
        "height": 540,
        "quality": 60,
        "drop": 4,
    },
    "monitor": {
        "label": "monitor",
        "distribution": "mjpeg",
        "fps": 5,
        "width": 1280,
        "height": 720,
        "quality": 70,
        "drop": 4,
    },
    "mobile": {
        "label": "mobile",
        "distribution": "mjpeg",
        "fps": 4,
        "width": 640,
        "height": 360,
        "quality": 55,
        "drop": 5,
    },
}


def normalize_stream_profile_name(profile: str | None) -> str:
    value = str(profile or "").strip().lower()
    return value if value in STREAM_DISTRIBUTION_PROFILES else DEFAULT_STREAM_PROFILE


def list_stream_profiles() -> list[Dict[str, Any]]:
    return [
        {"id": profile_id, **config}
        for profile_id, config in STREAM_DISTRIBUTION_PROFILES.items()
    ]


def resolve_stream_profile(profile: str | None, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile_id = normalize_stream_profile_name(profile)
    base = dict(STREAM_DISTRIBUTION_PROFILES[profile_id])
    for key in ("fps", "width", "height", "quality", "drop"):
        value = (overrides or {}).get(key)
        if value is not None and value != "":
            base[key] = int(value)
    base["id"] = profile_id
    return base
