from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import bounded_stream_fps, next_stream_frame_delay


def main() -> None:
    if bounded_stream_fps(60) != 30 or bounded_stream_fps(0) != 1 or bounded_stream_fps("24") != 24:
        raise SystemExit("preview FPS capability bounds are inconsistent")
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

    print({
        "ok": True,
        "maximum_stream_fps": 30,
        "decoder_time_deducted": True,
        "late_deadline_reset": True,
    })


if __name__ == "__main__":
    main()
