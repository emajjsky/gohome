from __future__ import annotations

from typing import Any


PRIVACY_MODES = ("original", "person_blur", "skeleton")
PRIVACY_MODE_RANK = {mode: index for index, mode in enumerate(PRIVACY_MODES)}


def normalize_privacy_mode(value: Any, default: str = "original") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in PRIVACY_MODE_RANK else default


def stricter_privacy_mode(first: Any, second: Any) -> str:
    normalized_first = normalize_privacy_mode(first)
    normalized_second = normalize_privacy_mode(second)
    return max((normalized_first, normalized_second), key=PRIVACY_MODE_RANK.__getitem__)
