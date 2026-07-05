from __future__ import annotations

import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SAMPLES_ROOT = ROOT / "data" / "eval" / "samples"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def save_image(path: Path, frame: np.ndarray) -> None:
    import cv2  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame)
    if not ok:
        raise RuntimeError(f"failed to write {path}")


def normal_room(width: int = 640, height: int = 480) -> np.ndarray:
    import cv2  # type: ignore

    frame = np.full((height, width, 3), [118, 124, 119], dtype=np.uint8)
    frame[: int(height * 0.62), :] = [135, 141, 136]
    frame[int(height * 0.65) :, :] = [88, 94, 90]
    cv2.rectangle(frame, (30, 80), (230, 210), (190, 205, 205), -1)
    cv2.rectangle(frame, (280, 290), (580, 410), (70, 94, 124), -1)
    cv2.ellipse(frame, (430, 290), (150, 44), 0, 180, 360, (88, 120, 150), -1, cv2.LINE_AA)
    cv2.rectangle(frame, (420, 130), (460, 360), (84, 103, 92), -1)
    cv2.circle(frame, (440, 108), 58, (92, 145, 112), -1, cv2.LINE_AA)
    return frame


def person_scene() -> np.ndarray:
    import cv2  # type: ignore

    frame = normal_room()
    cv2.circle(frame, (315, 132), 34, (82, 148, 214), -1, cv2.LINE_AA)
    cv2.rectangle(frame, (292, 166), (338, 202), (78, 142, 204), -1)
    cv2.ellipse(frame, (320, 286), (70, 104), 0, 0, 360, (62, 96, 158), -1, cv2.LINE_AA)
    cv2.line(frame, (274, 250), (222, 330), (70, 88, 126), 15, cv2.LINE_AA)
    cv2.line(frame, (366, 252), (415, 326), (70, 88, 126), 15, cv2.LINE_AA)
    cv2.line(frame, (292, 374), (258, 456), (54, 70, 96), 16, cv2.LINE_AA)
    cv2.line(frame, (346, 374), (382, 456), (54, 70, 96), 16, cv2.LINE_AA)
    return frame


def black_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def fire_frame(shift: int = 0, *, red_light: bool = False, warm_light: bool = False) -> np.ndarray:
    import cv2  # type: ignore

    frame = normal_room()
    if red_light:
        cv2.circle(frame, (450, 250), 54, (24, 34, 230), -1, cv2.LINE_AA)
        return frame
    if warm_light:
        cv2.circle(frame, (450, 250), 76, (40, 130, 235), -1, cv2.LINE_AA)
        cv2.circle(frame, (450, 250), 42, (45, 170, 245), -1, cv2.LINE_AA)
        return frame

    y, x = np.indices((150, 110))
    pattern = ((x + shift) // 9 + (y + shift * 2) // 11) % 4
    fire_r = np.choose(pattern, [255, 238, 215, 185]).astype(np.uint8)
    fire_g = np.choose(pattern, [215, 176, 135, 96]).astype(np.uint8)
    fire_b = np.choose(pattern, [12, 20, 28, 10]).astype(np.uint8)
    patch = np.dstack([fire_b, fire_g, fire_r])
    top = 170 + shift
    left = 402 + shift
    frame[top : top + patch.shape[0], left : left + patch.shape[1]] = patch
    cv2.GaussianBlur(frame[top : top + 150, left : left + 110], (3, 3), 0, frame[top : top + 150, left : left + 110])
    return frame


def fall_negative_scene() -> np.ndarray:
    import cv2  # type: ignore

    frame = normal_room()
    cv2.ellipse(frame, (320, 300), (64, 96), 0, 0, 360, (72, 98, 150), -1, cv2.LINE_AA)
    cv2.circle(frame, (320, 180), 34, (82, 148, 214), -1, cv2.LINE_AA)
    return frame


def prepare_person() -> None:
    path = SAMPLES_ROOT / "person"
    save_image(path / "person_demo.jpg", person_scene())
    save_image(path / "no_person_black.jpg", black_frame())
    write_jsonl(
        path / "manifest.jsonl",
        [
            {"file": "person_demo.jpg", "person_present": True, "config": {"force_demo_vision": True}},
            {"file": "no_person_black.jpg", "person_present": False, "config": {"force_demo_vision": True}},
        ],
    )


def prepare_fire() -> None:
    path = SAMPLES_ROOT / "fire"
    save_image(path / "fire_static.jpg", fire_frame(0))
    save_image(path / "fire_prev.jpg", fire_frame(0))
    save_image(path / "fire_next.jpg", fire_frame(8))
    save_image(path / "red_light.jpg", fire_frame(red_light=True))
    save_image(path / "warm_light.jpg", fire_frame(warm_light=True))
    config = {
        "fire_score_threshold": 0.02,
        "fire_event_score_threshold": 0.02,
        "fire_motion_threshold": 0.001,
        "fire_temporal_threshold": 0.001,
    }
    write_jsonl(
        path / "manifest.jsonl",
        [
            {"file": "fire_static.jpg", "fire": True, "fire_event": False, "config": {"fire_score_threshold": 0.02}},
            {"file": "fire_next.jpg", "previous_file": "fire_prev.jpg", "fire": True, "fire_event": True, "config": config},
            {"file": "red_light.jpg", "fire": False, "fire_event": False},
            {"file": "warm_light.jpg", "fire": False, "fire_event": False},
        ],
    )


def prepare_fall() -> None:
    path = SAMPLES_ROOT / "fall"
    save_image(path / "normal_sitting.jpg", fall_negative_scene())
    save_image(path / "empty_black.jpg", black_frame())
    write_jsonl(
        path / "manifest.jsonl",
        [
            {"file": "normal_sitting.jpg", "fall": False, "config": {"force_demo_vision": True}},
            {"file": "empty_black.jpg", "fall": False, "config": {"force_demo_vision": True}},
        ],
    )


def prepare_pose() -> None:
    path = SAMPLES_ROOT / "pose"
    save_image(path / "person_demo.jpg", person_scene())
    save_image(path / "empty_black.jpg", black_frame())
    write_jsonl(
        path / "manifest.jsonl",
        [
            {"file": "person_demo.jpg", "pose_present": True},
            {"file": "empty_black.jpg", "pose_present": False},
        ],
    )


def main() -> None:
    prepare_person()
    prepare_fire()
    prepare_fall()
    prepare_pose()
    print(
        json.dumps(
            {
                "ok": True,
                "samples_root": str(SAMPLES_ROOT),
                "tasks": ["person", "fire", "fall", "pose"],
                "note": "These are synthetic smoke-test samples for tooling validation, not product accuracy benchmarks.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
