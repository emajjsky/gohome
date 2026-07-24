from __future__ import annotations


PHYSICAL_RECOVERY_POSTURES = frozenset({"standing", "sitting"})
TRANSITIONAL_LOW_POSTURES = frozenset({"bending", "squatting", "low_body"})
PHYSICAL_RECOVERY_MIN_CONFIDENCE = 0.45


def is_physical_recovery_posture(
    posture: str,
    confidence: float,
    *,
    frame_edge_clipped: bool = False,
) -> bool:
    return bool(
        str(posture or "").strip().lower() in PHYSICAL_RECOVERY_POSTURES
        and float(confidence or 0.0) >= PHYSICAL_RECOVERY_MIN_CONFIDENCE
        and not frame_edge_clipped
    )
