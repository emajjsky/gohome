from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.motion_gate import MotionGate


def main() -> None:
    gate = MotionGate(threshold=0.02)
    quiet = np.full((120, 160, 3), 80, dtype=np.uint8)
    moved = quiet.copy()
    moved[30:90, 50:110] = 230
    first = gate.update(9, quiet, frame_id="9-1")
    second = gate.update(9, quiet, frame_id="9-2")
    motion = gate.update(9, moved, frame_id="9-3")
    if first["detected"] or second["detected"] or not motion["detected"]:
        raise SystemExit(f"motion gate classification is incorrect: {first}, {second}, {motion}")
    if motion["frame_id"] != "9-3" or float(motion["motion_score"]) <= 0.02:
        raise SystemExit(f"motion gate did not preserve frame identity or score: {motion}")
    print({"ok": True, "motion_wakeup": True, "quiet_frames_suppressed": 2})


if __name__ == "__main__":
    main()
