from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent
from app.vision.person_yolo import PersonDetector


def main() -> None:
    agent = DetectAgent(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    gradient = np.tile(np.linspace(60, 132, 320, dtype=np.uint8), (240, 1))
    normal = np.dstack([gradient, np.roll(gradient, 24, axis=1), np.full_like(gradient, 96)])
    fire = normal.copy()
    fire[40:120, 180:260] = [20, 120, 230]
    seated_half_body = synthetic_seated_half_body_frame()

    black_result = agent.analyze_frame_with_config(black)
    fire_result = agent.analyze_frame_with_config(fire)
    demo_result = agent.analyze_frame_with_config(normal, config={"force_demo_vision": True})
    presence_result = analyze_with_mocked_yolo_miss(seated_half_body)
    blank_presence_result = analyze_with_mocked_yolo_miss(black)

    checks = {
        "black_screen": bool(black_result["black_screen"]),
        "fire_candidate": bool(fire_result["fire_candidate"]),
        "demo_person_count": demo_result.get("person_count"),
        "presence_person_count": presence_result.get("person_count"),
        "presence_enhanced": bool(presence_result.get("presence_enhanced")),
        "blank_presence_person_count": blank_presence_result.get("person_count"),
        "pipeline_version": fire_result.get("pipeline_version"),
        "algorithm_results": sorted((fire_result.get("algorithm_results") or {}).keys()),
    }
    expected_algorithms = ["activity", "fall", "fire", "person", "quality"]
    if not checks["black_screen"]:
        raise SystemExit("black screen check failed")
    if not checks["fire_candidate"]:
        raise SystemExit("fire candidate check failed")
    if checks["algorithm_results"] != expected_algorithms:
        raise SystemExit(f"algorithm result keys mismatch: {checks['algorithm_results']}")
    if not isinstance(checks["demo_person_count"], int) or checks["demo_person_count"] < 1:
        raise SystemExit("demo person check failed")
    if not isinstance(checks["presence_person_count"], int) or checks["presence_person_count"] < 1:
        raise SystemExit("seated half-body presence enhancement check failed")
    if not checks["presence_enhanced"]:
        raise SystemExit("presence enhancement flag check failed")
    if checks["blank_presence_person_count"] != 0:
        raise SystemExit("blank presence false-positive check failed")

    print(json.dumps({"ok": True, **checks}, ensure_ascii=False, indent=2))


def synthetic_seated_half_body_frame() -> np.ndarray:
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError:
        cv2 = None

    frame = np.full((480, 640, 3), [118, 124, 119], dtype=np.uint8)
    frame[:, :260] = [105, 113, 112]
    frame[320:480, :] = [86, 91, 86]
    if cv2 is None:
        frame[116:196, 380:460] = [86, 150, 214]
        frame[198:390, 330:525] = [62, 95, 150]
        frame[250:292, 288:440] = [84, 146, 205]
        return frame

    cv2.rectangle(frame, (300, 250), (560, 430), (58, 62, 66), -1)
    cv2.ellipse(frame, (420, 148), (43, 52), -8, 0, 360, (82, 148, 214), -1)
    cv2.rectangle(frame, (392, 190), (444, 224), (78, 142, 204), -1)
    cv2.ellipse(frame, (425, 312), (104, 122), 2, 0, 360, (62, 96, 158), -1)
    cv2.ellipse(frame, (343, 270), (35, 82), 22, 0, 360, (82, 148, 214), -1)
    cv2.circle(frame, (407, 143), 5, (35, 45, 55), -1)
    cv2.circle(frame, (434, 145), 5, (35, 45, 55), -1)
    return frame


def analyze_with_mocked_yolo_miss(frame: np.ndarray) -> dict:
    detector = PersonDetector(detector_backend="yolo", yolo_confidence=0.35)
    detector._detect_people_with_yolo = lambda frame, confidence=None: []  # type: ignore[method-assign]
    return detector.analyze(frame, {})


if __name__ == "__main__":
    main()
