from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent
from app.detect_agent import DetectAgent
from app.event_agent import EventAgent
from app.rule_engine import RuleEngine
from app.settings import settings
from app.storage import Storage


class NullNotifier:
    def send(self, **_kwargs: Any) -> None:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit one production fall event from a public validation sequence.")
    parser.add_argument("--samples-dir", type=Path, default=ROOT / "data/eval/samples/fall/ur_fall")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/eval/samples/fall/ur_fall/manifest.jsonl")
    parser.add_argument("--camera-id", type=int, default=0)
    parser.add_argument("--sequence", default="fall-01")
    parser.add_argument("--frame-delay", type=float, default=1.0)
    parser.add_argument("--repeat-last", type=int, default=8)
    parser.add_argument("--vision-verification-probe", action="store_true")
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def sequence_key(entry: dict[str, Any]) -> str:
    return "|".join([
        str(entry.get("source_dataset") or "dataset"),
        str(entry.get("subject") or ""),
        str(entry.get("category") or entry.get("sequence_kind") or "sequence"),
        str(entry.get("sequence_id") or entry.get("source_video") or entry.get("file") or "unknown"),
    ])


def sequence_order(entry: dict[str, Any]) -> float:
    for key in ("timestamp_seconds", "frame_number", "frame_index"):
        if entry.get(key) is not None:
            return float(entry[key])
    return 0.0


def expected_fall(entry: dict[str, Any]) -> bool:
    value = entry.get("fall", entry.get("label", False))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "positive", "pos"}


def select_sequence(entries: list[dict[str, Any]], requested: str) -> tuple[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(sequence_key(entry), []).append(entry)
    positives = [
        (key, sorted(group, key=sequence_order))
        for key, group in sorted(groups.items())
        if any(expected_fall(entry) for entry in group)
    ]
    for key, group in positives:
        if requested and requested.lower() in key.lower():
            return key, group
    if positives:
        return positives[0]
    raise RuntimeError("manifest has no positive fall sequence")


def make_agent() -> DetectAgent:
    return DetectAgent(
        black_brightness_threshold=settings.black_brightness_threshold,
        black_contrast_threshold=settings.black_contrast_threshold,
        motion_threshold=settings.motion_threshold,
        detector_backend=settings.detector_backend,
        yolo_model=settings.yolo_model,
        yolo_confidence=settings.yolo_confidence,
        yolo_imgsz=settings.yolo_imgsz,
        pose_enabled=True,
        pose_mode=settings.pose_mode,
        pose_runtime_backend=settings.pose_runtime_backend,
        pose_device=settings.pose_device,
        pose_fall_threshold=settings.pose_fall_threshold,
        pose_fall_min_confidence=settings.pose_fall_min_confidence,
        pose_fall_min_visible_keypoints=settings.pose_fall_min_visible_keypoints,
        pose_fall_min_core_keypoints=settings.pose_fall_min_core_keypoints,
        pose_det_frequency=1,
        pose_min_keypoint_confidence=settings.pose_min_keypoint_confidence,
        pose_max_poses=settings.pose_max_poses,
        pose_tracking=False,
        pose_cache_seconds=settings.pose_cache_seconds,
        pose_cache_max_motion=settings.pose_cache_max_motion,
        activity_window_seconds=settings.activity_window_seconds,
        activity_max_samples=settings.activity_max_samples,
    )


def main() -> None:
    import cv2  # type: ignore

    args = parse_args()
    storage = Storage(settings.db_path)
    cameras = [camera for camera in storage.list_cameras(include_secret=True) if camera.get("enabled")]
    if not cameras:
        raise RuntimeError("no enabled camera is available for validation event ownership")
    camera = next((item for item in cameras if int(item["id"]) == args.camera_id), cameras[0])
    camera_id = int(camera["id"])
    sequence_name, entries = select_sequence(load_manifest(args.manifest.resolve()), args.sequence)
    samples_dir = args.samples_dir.resolve()
    rules = storage.get_rules()
    if not rules.get("fall_detection_enabled"):
        raise RuntimeError("fall_detection_enabled must be true before validation")

    agent = make_agent()
    engine = RuleEngine()
    previous_frame = None
    last_frame = None
    matched_analysis = None
    matched_evaluation = None
    frame_rows: list[dict[str, Any]] = []
    processed_frames: list[dict[str, Any]] = []
    replay_entries = list(entries)
    if replay_entries:
        replay_entries.extend([replay_entries[-1]] * max(0, int(args.repeat_last)))

    for index, entry in enumerate(replay_entries, start=1):
        frame_path = Path(str(entry.get("file") or ""))
        if not frame_path.is_absolute():
            frame_path = samples_dir / frame_path
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise RuntimeError(f"cannot read validation frame: {frame_path}")
        config = {
            **rules,
            "camera_id": camera_id,
            "pose_detection_enabled": True,
            "pose_reuse_cache_only": False,
            "scene_context_enabled": True,
        }
        analysis = agent.analyze_frame_with_config(frame, previous_frame=previous_frame, config=config)
        evaluation = engine.evaluate_snapshot(
            camera,
            {"id": 900000 + index},
            analysis,
            rules,
        )
        fall_candidates = [candidate for candidate in evaluation.candidates if candidate.event_type == "fall_candidate"]
        frame_rows.append({
            "index": index,
            "file": str(frame_path),
            "fall_stage": evaluation.state.get("fall_stage"),
            "fall_score": analysis.get("fall_score"),
            "candidate_count": len(fall_candidates),
        })
        processed_frames.append({
            "frame": frame.copy(),
            "analysis": analysis,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
        last_frame = frame
        if fall_candidates:
            matched_analysis = analysis
            matched_evaluation = evaluation
            break
        previous_frame = frame
        time.sleep(max(0.2, float(args.frame_delay)))

    if matched_analysis is None or matched_evaluation is None or last_frame is None:
        raise RuntimeError(f"production rules did not emit fall_candidate for {sequence_name}")

    camera_agent = CameraAgent(settings.snapshot_dir)
    relative_path = camera_agent.snapshot_relative_path(camera_id)
    camera_agent.save_frame(last_frame, relative_path)
    height, width = last_frame.shape[:2]
    snapshot = storage.create_snapshot(
        camera_id=camera_id,
        image_path=relative_path,
        width=width,
        height=height,
        brightness=float(matched_analysis.get("brightness") or 0.0),
        motion_score=matched_analysis.get("motion_score"),
        tags=matched_analysis.get("tags") or [],
        person_count=matched_analysis.get("person_count"),
        analysis=matched_analysis,
    )
    evaluation_payload = matched_evaluation.to_dict()
    evaluation_payload["snapshot_id"] = int(snapshot["id"])
    for candidate in evaluation_payload.get("candidates") or []:
        candidate["snapshot_id"] = int(snapshot["id"])
    detection = storage.create_detection_result(
        camera_id=camera_id,
        snapshot_id=int(snapshot["id"]),
        captured_at=snapshot["captured_at"],
        width=width,
        height=height,
        analysis=matched_analysis,
    )
    persisted_evaluation = storage.create_rule_evaluation(
        camera_id=camera_id,
        snapshot_id=int(snapshot["id"]),
        detection_result_id=int(detection["id"]),
        evaluation=evaluation_payload,
        rule_set_version=str(rules.get("updated_at") or ""),
    )
    candidate = next(item for item in evaluation_payload["candidates"] if item.get("event_type") == "fall_candidate")
    validation = {
        "test_event": True,
        "mode": "public_dataset_replay",
        "dataset": "UR Fall Detection Dataset",
        "sequence": sequence_name,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "vision_verification_probe": bool(args.vision_verification_probe),
    }
    representative_indices = sorted({0, len(processed_frames) // 2, len(processed_frames) - 1})
    evidence_snapshots: list[dict[str, Any]] = []
    for position, frame_index in enumerate(representative_indices):
        item = processed_frames[frame_index]
        if frame_index == len(processed_frames) - 1:
            frame_snapshot = snapshot
        else:
            keyframe_path = camera_agent.snapshot_relative_path(camera_id)
            camera_agent.save_frame(item["frame"], keyframe_path)
            keyframe_height, keyframe_width = item["frame"].shape[:2]
            frame_snapshot = storage.create_snapshot(
                camera_id=camera_id,
                image_path=keyframe_path,
                width=keyframe_width,
                height=keyframe_height,
                brightness=float(item["analysis"].get("brightness") or 0.0),
                motion_score=item["analysis"].get("motion_score"),
                tags=item["analysis"].get("tags") or [],
                person_count=item["analysis"].get("person_count"),
                analysis=item["analysis"],
            )
        evidence_snapshots.append({
            "snapshot_id": int(frame_snapshot["id"]),
            "snapshot_path": frame_snapshot["image_path"],
            "observed_at": item["observed_at"],
            "postures": sorted({
                str(pose.get("posture") or "unknown")
                for pose in item["analysis"].get("poses") or []
            }),
            "role": "before" if position == 0 else "current" if position == len(representative_indices) - 1 else "transition",
        })
    candidate_payload = {
        **(candidate.get("payload") or {}),
        "validation": validation,
        "evaluation": {
            "camera_id": camera_id,
            "snapshot_id": int(snapshot["id"]),
            "evaluated_at": evaluation_payload.get("evaluated_at"),
            "state": evaluation_payload.get("state") or {},
        },
        "data_chain": {
            "detection_result_id": int(detection["id"]),
            "rule_evaluation_id": int(persisted_evaluation["id"]),
        },
    }
    evidence = candidate_payload.get("evidence") if isinstance(candidate_payload.get("evidence"), dict) else {}
    candidate_payload["evidence"] = {
        **evidence,
        "temporal_evidence_bundle": {
            **(evidence.get("temporal_evidence_bundle") if isinstance(evidence.get("temporal_evidence_bundle"), dict) else {}),
            "schema_version": "temporal-evidence-bundle-v1",
            "event_type": "fall_candidate",
            "window_started_at": evidence_snapshots[0]["observed_at"],
            "window_ended_at": evidence_snapshots[-1]["observed_at"],
            "sample_count": len(processed_frames),
            "snapshots": evidence_snapshots,
        },
    }
    candidate["payload"] = candidate_payload
    persisted_candidate = storage.create_event_candidate(
        camera_id=camera_id,
        detection_result_id=int(detection["id"]),
        rule_evaluation_id=int(persisted_evaluation["id"]),
        candidate=candidate,
        evaluated_at=evaluation_payload.get("evaluated_at"),
    )
    candidate_payload["data_chain"]["event_candidate_id"] = int(persisted_candidate["id"])
    event_agent = EventAgent(storage, NullNotifier(), settings.event_throttle_seconds)
    event = event_agent.emit(
        event_type="fall_candidate",
        summary="算法闭环验收：公开样本命中疑似跌倒",
        level="critical",
        camera=camera,
        snapshot_id=int(snapshot["id"]),
        detection_result_id=int(detection["id"]),
        rule_evaluation_id=int(persisted_evaluation["id"]),
        candidate_id=int(persisted_candidate["id"]),
        payload=candidate_payload,
        force=True,
    )
    if event is None:
        raise RuntimeError("validation event was not created")
    print(json.dumps({
        "ok": True,
        "event_id": event["id"],
        "event_type": event["type"],
        "camera_id": camera_id,
        "snapshot_path": event.get("snapshot_path"),
        "sequence": sequence_name,
        "frame_rows": frame_rows,
        "evidence_snapshots": evidence_snapshots,
        "vision_verification_probe": bool(args.vision_verification_probe),
        "upload_queue": storage.upload_queue_summary(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
