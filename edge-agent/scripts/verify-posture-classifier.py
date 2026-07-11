from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.posture import PostureClassifier


def points(**coordinates: tuple[float, float]) -> list[dict]:
    return [
        {"name": name, "x": xy[0], "y": xy[1], "confidence": 0.92, "visible": True}
        for name, xy in coordinates.items()
    ]


SAMPLES = {
    "standing": points(
        left_shoulder=(280, 80), right_shoulder=(360, 80),
        left_hip=(295, 180), right_hip=(345, 180),
        left_knee=(300, 270), right_knee=(340, 270),
        left_ankle=(300, 350), right_ankle=(340, 350),
    ),
    "sitting": points(
        left_shoulder=(250, 70), right_shoulder=(310, 70),
        left_hip=(265, 175), right_hip=(300, 175),
        left_knee=(365, 185), right_knee=(390, 185),
        left_ankle=(365, 305), right_ankle=(390, 305),
    ),
    "squatting": points(
        left_shoulder=(280, 80), right_shoulder=(350, 80),
        left_hip=(295, 210), right_hip=(340, 210),
        left_knee=(255, 250), right_knee=(385, 250),
        left_ankle=(290, 325), right_ankle=(350, 325),
    ),
    "bending": points(
        left_shoulder=(220, 135), right_shoulder=(270, 150),
        left_hip=(315, 210), right_hip=(350, 220),
        left_knee=(320, 300), right_knee=(350, 305),
        left_ankle=(320, 365), right_ankle=(350, 365),
    ),
    "lying": points(
        left_shoulder=(140, 175), right_shoulder=(145, 220),
        left_hip=(280, 180), right_hip=(285, 220),
        left_knee=(390, 185), right_knee=(395, 220),
        left_ankle=(510, 190), right_ankle=(515, 220),
    ),
    "upper_body": points(
        nose=(300, 50), left_shoulder=(260, 105), right_shoulder=(340, 105),
        left_elbow=(230, 170), right_elbow=(370, 170),
        left_wrist=(220, 235), right_wrist=(380, 235),
    ),
}


def main() -> None:
    classifier = PostureClassifier()
    results = {name: classifier.classify(sample) for name, sample in SAMPLES.items()}
    for expected, result in results.items():
        if result["label"] != expected:
            raise SystemExit(f"expected {expected}, got {result}")
        if result["confidence"] < 0.40:
            raise SystemExit(f"posture confidence too low for {expected}: {result}")
    unknown = classifier.classify(points(nose=(10, 10), left_eye=(9, 9), right_eye=(11, 9)))
    if unknown["label"] != "unknown":
        raise SystemExit(f"insufficient skeleton must be unknown: {unknown}")
    print(json.dumps({"ok": True, "labels": {key: value["confidence"] for key, value in results.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
