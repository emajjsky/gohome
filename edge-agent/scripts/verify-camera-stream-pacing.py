from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import next_stream_frame_delay
from app.video_profiles import STREAM_DISTRIBUTION_PROFILES


def main() -> None:
    delay, next_deadline = next_stream_frame_delay(
        previous_deadline=100.0,
        now=100.04,
        frame_interval=0.125,
    )
    if abs(delay - 0.085) > 0.0001:
        raise SystemExit(f"decoder time was not deducted from pacing delay: {delay}")
    if abs(next_deadline - 100.125) > 0.0001:
        raise SystemExit(f"frame deadline drifted: {next_deadline}")

    delay, next_deadline = next_stream_frame_delay(
        previous_deadline=100.0,
        now=100.40,
        frame_interval=0.125,
    )
    if delay != 0:
        raise SystemExit(f"late frames must not sleep again: {delay}")
    if abs(next_deadline - 100.40) > 0.0001:
        raise SystemExit(f"late stream did not reset its deadline: {next_deadline}")

    for profile_id, profile in STREAM_DISTRIBUTION_PROFILES.items():
        if int(profile["fps"]) != 8:
            raise SystemExit(f"{profile_id} profile is not unified at 8 FPS")
        if int(profile["drop"]) != 1:
            raise SystemExit(f"{profile_id} profile still drains multiple source frames")

    print({
        "ok": True,
        "target_fps": 8,
        "profiles": sorted(STREAM_DISTRIBUTION_PROFILES),
        "decoder_time_deducted": True,
        "late_deadline_reset": True,
    })


if __name__ == "__main__":
    main()
