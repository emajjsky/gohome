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
from eval_vision_common import (
    audit_split_integrity,
    canonical_hash,
    classification_metrics,
    dataset_metadata,
    failure_lists,
    filter_entries_by_split,
    latency_metrics,
    quality_claim_gate,
    reproducibility_metadata,
    row_dimensions,
    stratified_metrics,
)


REPORT_SCHEMA_VERSION = "gohome-fall-sequence-eval-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the formal fall state machine over ordered frame sequences.")
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--split", default="", choices=["", "train", "validation", "test"])
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
    parser.add_argument("--quality-min-positive", type=int, default=30)
    parser.add_argument("--quality-min-negative", type=int, default=50)
    parser.add_argument("--quality-min-datasets", type=int, default=3)
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def sequence_key(entry: dict[str, Any]) -> str:
    dimensions = row_dimensions(entry)
    sequence_id = dimensions["sequence_id"] or str(entry.get("file") or "unknown")
    return "|".join([
        dimensions["dataset"],
        dimensions["subject"],
        dimensions["category"],
        sequence_id,
    ])


def sequence_order(entry: dict[str, Any]) -> float:
    for key in ("timestamp_seconds", "frame_number", "frame_index"):
        value = entry.get(key)
        if value is not None:
            return float(value)
    return 0.0


def frame_fall_label(entry: dict[str, Any]) -> bool | None:
    value = entry.get("fall", entry.get("label"))
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "positive", "pos"}:
        return True
    if lowered in {"0", "false", "no", "negative", "neg"}:
        return False
    return None


def sequence_label(entries: list[dict[str, Any]]) -> bool | None:
    labels = [frame_fall_label(entry) for entry in entries]
    labeled = [label for label in labels if label is not None]
    if not labeled:
        return None
    return any(labeled)


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


def evaluation_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "black_brightness_threshold": 18,
        "black_contrast_threshold": 4,
        "motion_threshold": 0.015,
        "detector_backend": args.detector_backend,
        "yolo_model": args.yolo_model,
        "yolo_confidence": args.yolo_confidence,
        "yolo_imgsz": args.yolo_imgsz,
        "pose_enabled": True,
        "pose_runtime_backend": "onnxruntime",
        "pose_device": "cpu",
        "pose_det_frequency": 1,
        "pose_fall_threshold": args.pose_fall_threshold,
        "pose_fall_min_confidence": args.pose_fall_min_confidence,
        "pose_fall_min_visible_keypoints": args.pose_fall_min_visible_keypoints,
        "pose_fall_min_core_keypoints": args.pose_fall_min_core_keypoints,
        "pose_min_keypoint_confidence": 0.30,
        "pose_max_poses": 3,
        "pose_tracking": False,
        "pose_cache_seconds": 1.8,
        "pose_cache_max_motion": 0.06,
        "inference_backend": "auto",
        "hailo_pose_model": "/usr/share/hailo-models/yolov8s_pose_h8.hef",
        "hailo_pose_confidence": 0.25,
        "hailo_pose_nms_iou": 0.70,
        "hailo_object_mode": "auto",
        "hailo_object_model": "/usr/share/hailo-models/yolov8s_h8.hef",
        "hailo_object_confidence": 0.30,
        "hailo_object_interval_seconds": 1.0,
        "hailo_retry_seconds": 30.0,
        "context_detection_interval_seconds": 3.0,
        "fall_score_threshold": args.fall_score_threshold,
        "fall_confirm_frames": max(2, args.fall_confirm_frames),
        "fall_transition_window_seconds": args.fall_transition_window_seconds,
        "fall_min_vertical_drop": args.fall_min_vertical_drop,
        "fall_transition_motion_score": args.fall_transition_motion_score,
        "requested_split": str(args.split or ""),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    import cv2  # type: ignore

    samples_dir = args.samples_dir.resolve()
    manifest_path = args.manifest.resolve()
    all_entries = load_manifest(manifest_path)
    entries = filter_entries_by_split(all_entries, str(args.split or ""))
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
    rows: list[dict[str, Any]] = []
    runtime_backend: dict[str, Any] = {}
    try:
        for camera_id, (key, sequence) in enumerate(sorted(groups.items()), start=1):
            ordered = sorted(sequence, key=sequence_order)
            expected = sequence_label(ordered)
            dimensions = row_dimensions(ordered[0])
            sequence_splits = {str(entry.get("split") or "").strip().lower() for entry in ordered}
            previous_frame = None
            predicted = False
            stages = []
            scene_suppressed_frames = 0
            transition_frames = 0
            errors = []
            frame_diagnostics = []
            started = time.perf_counter()
            if len(sequence_splits) > 1:
                errors.append(f"sequence spans multiple splits: {sorted(sequence_splits)}")
            if any(frame_fall_label(entry) is None for entry in ordered):
                errors.append("sequence contains unlabeled frames")
            for frame_index, entry in enumerate(ordered, start=1):
                path = Path(str(entry.get("file") or ""))
                if not path.is_absolute():
                    path = samples_dir / path
                frame = cv2.imread(str(path))
                if frame is None:
                    errors.append(f"missing frame: {path}")
                    continue
                frame_config = {
                    **rules,
                    **(entry.get("config") if isinstance(entry.get("config"), dict) else {}),
                    "camera_id": camera_id,
                    "pose_detection_enabled": True,
                    "pose_reuse_cache_only": False,
                    "scene_context_enabled": True,
                }
                analysis = agent.analyze_frame_with_config(frame, previous_frame=previous_frame, config=frame_config)
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
                target = evaluation.state.get("fall_target") if isinstance(evaluation.state.get("fall_target"), dict) else None
                transition = evaluation.state.get("fall_transition") if isinstance(evaluation.state.get("fall_transition"), dict) else {}
                frame_diagnostics.append({
                    "file": str(entry.get("file") or ""),
                    "expected_fall": frame_fall_label(entry),
                    "stage": stage,
                    "person_count": int(analysis.get("person_count") or 0),
                    "display_pose_count": int(analysis.get("display_pose_count") or analysis.get("pose_count") or 0),
                    "fall_evidence_pose_count": int(analysis.get("fall_evidence_pose_count") or 0),
                    "fall_candidate": bool(analysis.get("fall_candidate")),
                    "pose_fall_candidate": bool(analysis.get("pose_fall_candidate")),
                    "fall_score": round(float(analysis.get("fall_score") or 0.0), 4),
                    "pose_fall_score": round(float(analysis.get("pose_fall_score") or 0.0), 4),
                    "target": target,
                    "transition_confirmed": bool(evaluation.state.get("fall_transition_confirmed")),
                    "vertical_drop": transition.get("vertical_drop"),
                    "motion_score": analysis.get("motion_score"),
                    "scene_suppressed": bool(evaluation.state.get("fall_scene_suppressed")),
                    "candidate_types": [candidate.event_type for candidate in evaluation.candidates],
                })
                previous_frame = frame
            rows.append({
                "file": key,
                "sequence": key,
                "expected": expected,
                "predicted": predicted,
                "frame_count": len(ordered),
                "stages": stages,
                "scene_suppressed_frames": scene_suppressed_frames,
                "transition_frames": transition_frames,
                "frame_diagnostics": frame_diagnostics,
                "error": "; ".join(errors),
                "errors": errors,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                **dimensions,
            })
        runtime_backend = agent.runtime_status()
    finally:
        agent.close()

    metrics = classification_metrics(rows)
    config = evaluation_config(args)
    dataset = dataset_metadata(samples_dir, all_entries, manifest_path)
    split_integrity = audit_split_integrity(all_entries)
    quality_claim = quality_claim_gate(
        metrics=metrics,
        rows=rows,
        requested_split=str(args.split or ""),
        split_integrity=split_integrity,
        dataset_fingerprint=str(dataset.get("fingerprint") or ""),
        minimum_positive=max(1, int(args.quality_min_positive)),
        minimum_negative=max(1, int(args.quality_min_negative)),
        minimum_datasets=max(1, int(args.quality_min_datasets)),
        sequence_evaluation=True,
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "task": "fall_sequence",
        "samples_dir": str(samples_dir),
        "manifest": str(manifest_path),
        "count": len(rows),
        "sequence_count": len(rows),
        "metrics": metrics,
        "stratified_metrics": stratified_metrics(rows),
        "failures": failure_lists(rows),
        "latency": latency_metrics([int(row["latency_ms"]) for row in rows]),
        "config": config,
        "config_fingerprint": canonical_hash(config),
        "reproducibility": reproducibility_metadata(config=config, dataset=dataset, runtime_backend=runtime_backend),
        "split_integrity": split_integrity,
        "quality_claim": quality_claim,
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
        "quality_claim_ready": report["quality_claim"]["ready"],
        "report": report["report"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
