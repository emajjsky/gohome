from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "eval" / "reports"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent
from app.rule_engine import RuleEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the formal fall state machine over ordered frame sequences.")
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--detector-backend", default="yolo", choices=["basic", "yolo"])
    parser.add_argument("--yolo-model", default="yolo11n.pt")
    parser.add_argument("--yolo-confidence", type=float, default=0.20)
    parser.add_argument("--yolo-imgsz", type=int, default=416)
    parser.add_argument("--pose-fall-threshold", type=float, default=0.78)
    parser.add_argument("--pose-fall-min-confidence", type=float, default=0.36)
    parser.add_argument("--pose-fall-min-visible-keypoints", type=int, default=8)
    parser.add_argument("--pose-fall-min-core-keypoints", type=int, default=2)
    parser.add_argument("--fall-score-threshold", type=float, default=0.50)
    parser.add_argument("--fall-confirm-frames", type=int, default=2)
    parser.add_argument("--fall-transition-window-seconds", type=int, default=20)
    parser.add_argument("--fall-min-vertical-drop", type=float, default=0.12)
    parser.add_argument("--fall-transition-motion-score", type=float, default=0.02)
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def sequence_key(entry: dict[str, Any]) -> str:
    dataset = str(entry.get("source_dataset") or "dataset")
    subject = str(entry.get("subject") or "")
    category = str(entry.get("category") or entry.get("sequence_kind") or "sequence")
    sequence_id = str(entry.get("sequence_id") or entry.get("source_video") or entry.get("file") or "unknown")
    return "|".join([dataset, subject, category, sequence_id])


def sequence_order(entry: dict[str, Any]) -> float:
    for key in ("timestamp_seconds", "frame_number", "frame_index"):
        value = entry.get(key)
        if value is not None:
            return float(value)
    return 0.0


def expected_fall(entry: dict[str, Any]) -> bool:
    value = entry.get("fall", entry.get("label", False))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "positive", "pos"}


def make_agent(args: argparse.Namespace) -> DetectAgent:
    return DetectAgent(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend=args.detector_backend,
        yolo_model=args.yolo_model,
        yolo_confidence=args.yolo_confidence,
        yolo_imgsz=args.yolo_imgsz,
        pose_enabled=True,
        pose_fall_threshold=args.pose_fall_threshold,
        pose_fall_min_confidence=args.pose_fall_min_confidence,
        pose_fall_min_visible_keypoints=args.pose_fall_min_visible_keypoints,
        pose_fall_min_core_keypoints=args.pose_fall_min_core_keypoints,
        pose_det_frequency=1,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    import cv2  # type: ignore

    samples_dir = args.samples_dir.resolve()
    entries = load_manifest(args.manifest.resolve())
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(sequence_key(entry), []).append(entry)
    agent = make_agent(args)
    engine = RuleEngine()
    rules = {
        "black_screen_enabled": False,
        "person_detection_enabled": True,
        "fall_detection_enabled": True,
        "fall_score_threshold": args.fall_score_threshold,
        "fall_confirm_frames": max(2, args.fall_confirm_frames),
        "fall_confirm_seconds": 0,
        "fall_recover_frames": 2,
        "fall_transition_window_seconds": args.fall_transition_window_seconds,
        "fall_min_vertical_drop": args.fall_min_vertical_drop,
        "fall_transition_motion_score": args.fall_transition_motion_score,
        "fire_detection_enabled": False,
        "activity_detection_enabled": False,
        "no_motion_enabled": False,
        "no_person_seconds": 300,
    }
    metrics = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "errors": 0}
    rows = []
    for camera_id, (key, sequence) in enumerate(sorted(groups.items()), start=1):
        ordered = sorted(sequence, key=sequence_order)
        expected = any(expected_fall(entry) for entry in ordered)
        previous_frame = None
        predicted = False
        stages = []
        scene_suppressed_frames = 0
        transition_frames = 0
        errors = []
        started = time.perf_counter()
        for frame_index, entry in enumerate(ordered, start=1):
            path = Path(str(entry.get("file") or ""))
            if not path.is_absolute():
                path = samples_dir / path
            frame = cv2.imread(str(path))
            if frame is None:
                errors.append(f"missing frame: {path}")
                continue
            config = {
                **rules,
                **(entry.get("config") if isinstance(entry.get("config"), dict) else {}),
                "camera_id": camera_id,
                "pose_detection_enabled": True,
                "pose_reuse_cache_only": False,
                "scene_context_enabled": True,
            }
            analysis = agent.analyze_frame_with_config(frame, previous_frame=previous_frame, config=config)
            evaluation = engine.evaluate_snapshot(
                {"id": camera_id, "name": key},
                {"id": camera_id * 1000 + frame_index},
                analysis,
                rules,
            )
            stage = str(evaluation.state.get("fall_stage") or "clear")
            stages.append(stage)
            scene_suppressed_frames += int(bool(evaluation.state.get("fall_scene_suppressed")))
            transition_frames += int(bool(evaluation.state.get("fall_transition_confirmed")))
            predicted = predicted or any(candidate.event_type == "fall_candidate" for candidate in evaluation.candidates)
            previous_frame = frame
        if errors:
            metrics["errors"] += len(errors)
        if predicted and expected:
            metrics["tp"] += 1
        elif predicted and not expected:
            metrics["fp"] += 1
        elif not predicted and expected:
            metrics["fn"] += 1
        else:
            metrics["tn"] += 1
        rows.append({
            "sequence": key,
            "expected": expected,
            "predicted": predicted,
            "frame_count": len(ordered),
            "stages": stages,
            "scene_suppressed_frames": scene_suppressed_frames,
            "transition_frames": transition_frames,
            "errors": errors,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        })

    tp, fp, fn, tn = metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]
    report = {
        "schema_version": "gohome-fall-sequence-eval-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task": "fall_sequence",
        "samples_dir": str(samples_dir),
        "sequence_count": len(rows),
        "metrics": {
            **metrics,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        },
        "config": {
            "yolo_model": args.yolo_model,
            "yolo_confidence": args.yolo_confidence,
            "yolo_imgsz": args.yolo_imgsz,
            "pose_fall_threshold": args.pose_fall_threshold,
            "fall_confirm_frames": max(2, args.fall_confirm_frames),
            "fall_transition_window_seconds": args.fall_transition_window_seconds,
            "fall_min_vertical_drop": args.fall_min_vertical_drop,
            "fall_transition_motion_score": args.fall_transition_motion_score,
        },
        "rows": rows,
    }
    report_path = args.report
    if report_path is None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        dataset_name = samples_dir.name.replace("_", "-")
        report_path = REPORT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_fall_sequence_{dataset_name}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> None:
    report = run(parse_args())
    print(json.dumps({
        "ok": report["metrics"]["errors"] == 0,
        "task": report["task"],
        "sequence_count": report["sequence_count"],
        "metrics": report["metrics"],
        "report": report["report"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
