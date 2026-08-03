from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "eval"
REPORT_DIR = DATA_ROOT / "reports"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
REPORT_SCHEMA_VERSION = "gohome-vision-eval-report-v2"
ALGORITHM_SOURCE_FILES = tuple([
    ROOT / "app" / "detect_agent.py",
    ROOT / "app" / "rule_engine.py",
] + sorted((ROOT / "app" / "vision").glob("*.py")))


@dataclass
class EvalSample:
    path: Path
    entry: dict[str, Any]
    frame_index: int | None = None
    timestamp_ms: int | None = None
    previous_frame: Any | None = None


def parse_common_args(description: str, task: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--samples-dir", type=Path, default=DATA_ROOT / "samples" / task)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--split", default="", choices=["", "train", "validation", "test"])
    parser.add_argument("--detector-backend", default="basic", choices=["basic", "yolo"])
    parser.add_argument("--yolo-model", default="yolo11n.pt")
    parser.add_argument("--yolo-confidence", type=float, default=0.20)
    parser.add_argument("--yolo-imgsz", type=int, default=416)
    parser.add_argument("--pose-enabled", action="store_true")
    parser.add_argument("--pose-mode", default="lightweight")
    parser.add_argument("--pose-device", default="cpu")
    parser.add_argument("--pose-det-frequency", type=int, default=1)
    parser.add_argument("--pose-fall-threshold", type=float, default=0.78)
    parser.add_argument("--pose-fall-min-confidence", type=float, default=0.36)
    parser.add_argument("--pose-fall-min-visible-keypoints", type=int, default=8)
    parser.add_argument("--pose-fall-min-core-keypoints", type=int, default=2)
    parser.add_argument("--max-video-frames", type=int, default=120)
    parser.add_argument("--video-stride", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quality-min-positive", type=int, default=30)
    parser.add_argument("--quality-min-negative", type=int, default=50)
    parser.add_argument("--quality-min-datasets", type=int, default=3)
    return parser


def make_agent(args: argparse.Namespace) -> DetectAgent:
    return DetectAgent(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend=args.detector_backend,
        yolo_model=args.yolo_model,
        yolo_confidence=args.yolo_confidence,
        yolo_imgsz=args.yolo_imgsz,
        pose_enabled=bool(args.pose_enabled),
        pose_mode=args.pose_mode,
        pose_device=args.pose_device,
        pose_det_frequency=args.pose_det_frequency,
        pose_fall_threshold=args.pose_fall_threshold,
        pose_fall_min_confidence=args.pose_fall_min_confidence,
        pose_fall_min_visible_keypoints=args.pose_fall_min_visible_keypoints,
        pose_fall_min_core_keypoints=args.pose_fall_min_core_keypoints,
    )


def load_manifest(path: Path | None, samples_dir: Path) -> list[dict[str, Any]]:
    manifest_path = path
    if manifest_path is None:
        for candidate in [samples_dir / "manifest.jsonl", samples_dir / "manifest.json"]:
            if candidate.exists():
                manifest_path = candidate
                break
    if manifest_path is None or not manifest_path.exists():
        return [{"file": str(media_path.relative_to(samples_dir))} for media_path in discover_media(samples_dir)]
    if manifest_path.suffix.lower() == ".jsonl":
        entries = []
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                entries.append(json.loads(line))
        return entries
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return list(payload.get("samples") or [])


def discover_media(samples_dir: Path) -> list[Path]:
    if not samples_dir.exists():
        return []
    media = [
        path
        for path in samples_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    ]
    return sorted(media)


def resolve_sample_path(samples_dir: Path, entry: dict[str, Any]) -> Path:
    raw = str(entry.get("file") or entry.get("path") or "").strip()
    if not raw:
        raise ValueError(f"sample entry missing file: {entry}")
    path = Path(raw)
    return path if path.is_absolute() else samples_dir / path


def expected_bool(entry: dict[str, Any], keys: Iterable[str]) -> bool | None:
    for key in keys:
        if key in entry:
            value = entry[key]
            if value is None or value == "":
                return None
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            lowered = str(value).strip().lower()
            if lowered in {"1", "true", "yes", "positive", "pos", "hit", "present"}:
                return True
            if lowered in {"0", "false", "no", "negative", "neg", "clear", "absent"}:
                return False
    return None


def iter_samples(
    entries: list[dict[str, Any]],
    samples_dir: Path,
    *,
    max_video_frames: int,
    video_stride: int,
) -> Iterable[EvalSample]:
    import cv2  # type: ignore

    for entry in entries:
        path = resolve_sample_path(samples_dir, entry)
        if not path.exists():
            yield EvalSample(path=path, entry={**entry, "_error": "missing_file"})
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            frame = cv2.imread(str(path))
            if frame is None:
                yield EvalSample(path=path, entry={**entry, "_error": "image_read_failed"})
                continue
            yield EvalSample(path=path, entry=entry, frame_index=0, timestamp_ms=0, previous_frame=None)
            continue
        if suffix not in VIDEO_EXTENSIONS:
            continue
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            yield EvalSample(path=path, entry={**entry, "_error": "video_open_failed"})
            continue
        try:
            frame_index = 0
            emitted = 0
            previous = None
            while emitted < max_video_frames:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if frame_index % max(1, video_stride) == 0:
                    timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                    yield EvalSample(
                        path=path,
                        entry=entry,
                        frame_index=frame_index,
                        timestamp_ms=timestamp_ms,
                        previous_frame=previous,
                    )
                    emitted += 1
                    previous = frame.copy()
                frame_index += 1
        finally:
            cap.release()


def analyze_frame(agent: DetectAgent, sample: EvalSample) -> tuple[dict[str, Any] | None, str, int]:
    import cv2  # type: ignore

    if sample.entry.get("_error"):
        return None, str(sample.entry["_error"]), 0
    frame = cv2.imread(str(sample.path)) if sample.path.suffix.lower() in IMAGE_EXTENSIONS else None
    if frame is None and sample.path.suffix.lower() in VIDEO_EXTENSIONS:
        frame = read_video_frame(sample.path, int(sample.frame_index or 0))
    if frame is None:
        return None, "frame_read_failed", 0
    previous_frame = sample.previous_frame
    previous_file = str(sample.entry.get("previous_file") or "").strip()
    if previous_file:
        previous_path = Path(previous_file)
        if not previous_path.is_absolute():
            previous_path = sample.path.parent / previous_path
        previous_frame = cv2.imread(str(previous_path))
        if previous_frame is None:
            return None, "previous_frame_read_failed", 0
    config = sample.entry.get("config") if isinstance(sample.entry.get("config"), dict) else {}
    started = time.perf_counter()
    result = agent.analyze_frame_with_config(frame, previous_frame=previous_frame, config=config)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result, "", elapsed_ms


def read_video_frame(path: Path, target_index: int) -> Any | None:
    import cv2  # type: ignore

    cap = cv2.VideoCapture(str(path))
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_index)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def run_eval(
    *,
    task: str,
    args: argparse.Namespace,
    label_keys: list[str],
    predict: Callable[[dict[str, Any]], bool],
    detail: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    args.samples_dir = args.samples_dir.resolve()
    all_entries = load_manifest(args.manifest, args.samples_dir)
    entries = filter_entries_by_split(all_entries, str(args.split or ""))
    if args.limit:
        entries = entries[: max(1, int(args.limit))]
    agent = make_agent(args)
    rows: list[dict[str, Any]] = []
    latencies: list[int] = []
    runtime_backend: dict[str, Any] = {}
    try:
        for sample in iter_samples(
            entries,
            args.samples_dir,
            max_video_frames=int(args.max_video_frames),
            video_stride=int(args.video_stride),
        ):
            result, error, elapsed_ms = analyze_frame(agent, sample)
            expected = expected_bool(sample.entry, label_keys)
            predicted = bool(predict(result or {})) if result is not None else False
            latencies.append(elapsed_ms)
            rows.append({
                "file": str(sample.path),
                "frame_index": sample.frame_index,
                "timestamp_ms": sample.timestamp_ms,
                "expected": expected,
                "predicted": predicted,
                "latency_ms": elapsed_ms,
                "error": error,
                **row_dimensions(sample.entry),
                "detail": detail(result or {}),
            })
        runtime_backend = agent.runtime_status()
    finally:
        agent.close()

    config = evaluation_config(args)
    integrity = audit_split_integrity(all_entries)
    dataset = dataset_metadata(args.samples_dir, all_entries, args.manifest)
    metrics = classification_metrics(rows)
    quality_gate = quality_claim_gate(
        metrics=metrics,
        rows=rows,
        requested_split=str(args.split or ""),
        split_integrity=integrity,
        dataset_fingerprint=str(dataset.get("fingerprint") or ""),
        minimum_positive=max(1, int(args.quality_min_positive)),
        minimum_negative=max(1, int(args.quality_min_negative)),
        minimum_datasets=max(1, int(args.quality_min_datasets)),
        sequence_evaluation=task != "fall",
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "task": task,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "samples_dir": str(args.samples_dir),
        "count": len(rows),
        "metrics": metrics,
        "stratified_metrics": stratified_metrics(rows),
        "failures": failure_lists(rows),
        "latency": latency_metrics(latencies),
        "config": config,
        "reproducibility": reproducibility_metadata(config=config, dataset=dataset, runtime_backend=runtime_backend),
        "split_integrity": integrity,
        "quality_claim": quality_gate,
        "rows": rows,
    }
    write_report(task, report, args.report)
    return report


def filter_entries_by_split(entries: list[dict[str, Any]], requested_split: str) -> list[dict[str, Any]]:
    requested = requested_split.strip().lower()
    if not requested:
        return list(entries)
    return [entry for entry in entries if str(entry.get("split") or "").strip().lower() == requested]


def row_dimensions(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "dataset": str(entry.get("source_dataset") or entry.get("dataset") or "local"),
        "category": str(entry.get("category") or entry.get("sequence_kind") or entry.get("posture") or "uncategorized"),
        "subject": str(entry.get("subject") or entry.get("family_id") or ""),
        "viewpoint": str(entry.get("viewpoint") or entry.get("camera_view") or ""),
        "split": str(entry.get("split") or "").strip().lower(),
        "sequence_id": str(entry.get("sequence_id") or entry.get("source_video") or entry.get("clip_id") or ""),
    }


def empty_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "unlabeled": 0, "errors": 0}


def confusion_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = empty_counts()
    for row in rows:
        if row.get("error"):
            counts["errors"] += 1
            continue
        expected = row.get("expected")
        predicted = bool(row.get("predicted"))
        if expected is None:
            counts["unlabeled"] += 1
        elif predicted and bool(expected):
            counts["tp"] += 1
        elif predicted:
            counts["fp"] += 1
        elif bool(expected):
            counts["fn"] += 1
        else:
            counts["tn"] += 1
    return counts


def classification_metrics(rows_or_counts: Iterable[dict[str, Any]] | dict[str, int]) -> dict[str, Any]:
    counts = dict(rows_or_counts) if isinstance(rows_or_counts, dict) else confusion_counts(rows_or_counts)
    tp = int(counts.get("tp") or 0)
    fp = int(counts.get("fp") or 0)
    tn = int(counts.get("tn") or 0)
    fn = int(counts.get("fn") or 0)
    labeled = tp + fp + tn + fn
    positive = tp + fn
    negative = tn + fp
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, positive)
    specificity = safe_ratio(tn, negative)
    accuracy = safe_ratio(tp + tn, labeled)
    f1 = safe_ratio(2 * tp, 2 * tp + fp + fn)
    balanced_accuracy = None if recall is None or specificity is None else (recall + specificity) / 2
    return {
        **{key: int(counts.get(key) or 0) for key in empty_counts()},
        "support": {"labeled": labeled, "positive": positive, "negative": negative},
        "precision": precision,
        "recall": recall,
        "sensitivity": recall,
        "specificity": specificity,
        "f1": f1,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "false_positive_rate": safe_ratio(fp, negative),
        "false_negative_rate": safe_ratio(fn, positive),
        "confidence_intervals_95": {
            "precision": wilson_interval(tp, tp + fp),
            "recall": wilson_interval(tp, positive),
            "specificity": wilson_interval(tn, negative),
            "accuracy": wilson_interval(tp + tn, labeled),
        },
    }


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) / total) + (z * z / (4 * total * total))) / denominator
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


def stratified_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for dimension in ("dataset", "category", "subject", "viewpoint"):
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            value = str(row.get(dimension) or "").strip()
            if value:
                groups.setdefault(value, []).append(row)
        result[dimension] = {key: classification_metrics(group) for key, group in sorted(groups.items())}
    return result


def failure_lists(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    fields = ("file", "sequence_id", "dataset", "category", "subject", "viewpoint", "split", "error")
    false_positives = [row for row in rows if not row.get("error") and row.get("expected") is False and row.get("predicted")]
    false_negatives = [row for row in rows if not row.get("error") and row.get("expected") is True and not row.get("predicted")]
    errors = [row for row in rows if row.get("error")]
    return {
        "false_positives": [{key: row.get(key) for key in fields} for row in false_positives],
        "false_negatives": [{key: row.get(key) for key in fields} for row in false_negatives],
        "errors": [{key: row.get(key) for key in fields} for row in errors],
    }


def evaluation_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "black_brightness_threshold": 18,
        "black_contrast_threshold": 4,
        "motion_threshold": 0.015,
        "detector_backend": args.detector_backend,
        "yolo_model": args.yolo_model,
        "yolo_confidence": args.yolo_confidence,
        "yolo_imgsz": args.yolo_imgsz,
        "pose_enabled": bool(args.pose_enabled),
        "pose_mode": args.pose_mode,
        "pose_runtime_backend": "onnxruntime",
        "pose_device": args.pose_device,
        "pose_det_frequency": args.pose_det_frequency,
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
        "max_video_frames": args.max_video_frames,
        "video_stride": args.video_stride,
        "requested_split": str(args.split or ""),
    }


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataset_metadata(samples_dir: Path, entries: list[dict[str, Any]], manifest: Path | None) -> dict[str, Any]:
    files = []
    for entry in entries:
        try:
            path = resolve_sample_path(samples_dir, entry)
        except ValueError:
            continue
        try:
            stable_path = str(path.resolve().relative_to(samples_dir.resolve()))
        except ValueError:
            stable_path = str(path.resolve())
        files.append({
            "path": stable_path,
            "size": path.stat().st_size if path.exists() else None,
            "sha256": file_sha256(path) if path.exists() and path.is_file() else None,
        })
    normalized_entries = sorted(entries, key=lambda item: canonical_hash(item))
    fingerprint_payload = {"entries": normalized_entries, "files": sorted(files, key=lambda item: item["path"])}
    return {
        "manifest": str(manifest.resolve()) if manifest else None,
        "entry_count": len(entries),
        "file_count": len(files),
        "fingerprint": canonical_hash(fingerprint_payload),
    }


def audit_split_integrity(entries: list[dict[str, Any]]) -> dict[str, Any]:
    split_sequences: dict[str, set[str]] = {}
    split_subjects: dict[str, set[str]] = {}
    rows_without_split = []
    rows_without_sequence = []
    rows_without_subject = []
    for entry in entries:
        split = str(entry.get("split") or "").strip().lower()
        if not split:
            rows_without_split.append(str(entry.get("file") or ""))
            continue
        dimensions = row_dimensions(entry)
        sequence_id = "|".join([
            dimensions["dataset"],
            dimensions["subject"],
            dimensions["sequence_id"],
        ]) if dimensions["sequence_id"] else ""
        subject = dimensions["subject"]
        if sequence_id:
            split_sequences.setdefault(split, set()).add(sequence_id)
        else:
            rows_without_sequence.append(str(entry.get("file") or ""))
        if subject:
            split_subjects.setdefault(split, set()).add("|".join([dimensions["dataset"], subject]))
        else:
            rows_without_subject.append(str(entry.get("file") or ""))
    sequence_leakage = pairwise_overlap(split_sequences)
    subject_leakage = pairwise_overlap(split_subjects)
    split_names = sorted(set(split_sequences) | set(split_subjects) | {
        str(entry.get("split") or "").strip().lower() for entry in entries if entry.get("split")
    })
    return {
        "splits": split_names,
        "required_splits_present": {"train", "validation", "test"}.issubset(split_names),
        "sequence_leakage": sequence_leakage,
        "subject_leakage": subject_leakage,
        "sequence_disjoint": not sequence_leakage,
        "subject_disjoint": not subject_leakage,
        "rows_without_split": rows_without_split,
        "rows_without_sequence": rows_without_sequence,
        "rows_without_subject": rows_without_subject,
        "metadata_complete": not rows_without_split and not rows_without_sequence and not rows_without_subject,
    }


def pairwise_overlap(values: dict[str, set[str]]) -> list[dict[str, Any]]:
    overlaps = []
    names = sorted(values)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            shared = sorted(values[left] & values[right])
            if shared:
                overlaps.append({"splits": [left, right], "count": len(shared), "values": shared})
    return overlaps


def quality_claim_gate(
    *,
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    requested_split: str,
    split_integrity: dict[str, Any],
    dataset_fingerprint: str,
    minimum_positive: int,
    minimum_negative: int,
    minimum_datasets: int,
    sequence_evaluation: bool = True,
) -> dict[str, Any]:
    observed_splits = {str(row.get("split") or "") for row in rows}
    observed_datasets = {str(row.get("dataset") or "").strip() for row in rows if str(row.get("dataset") or "").strip()}
    checks = {
        "sequence_evaluation_for_temporal_claim": sequence_evaluation,
        "explicit_test_split": requested_split == "test" and observed_splits == {"test"},
        "all_rows_labeled": int(metrics.get("unlabeled") or 0) == 0,
        "all_rows_readable": int(metrics.get("errors") or 0) == 0,
        "minimum_positive_support": int((metrics.get("support") or {}).get("positive") or 0) >= minimum_positive,
        "minimum_negative_support": int((metrics.get("support") or {}).get("negative") or 0) >= minimum_negative,
        "required_splits_present": bool(split_integrity.get("required_splits_present")),
        "split_metadata_complete": bool(split_integrity.get("metadata_complete")),
        "sequence_disjoint": bool(split_integrity.get("sequence_disjoint")),
        "subject_disjoint": bool(split_integrity.get("subject_disjoint")),
        "minimum_dataset_support": len(observed_datasets) >= minimum_datasets,
        "dataset_fingerprint_present": bool(dataset_fingerprint),
    }
    return {
        "ready": bool(rows) and all(checks.values()),
        "checks": checks,
        "minimum": {"positive": minimum_positive, "negative": minimum_negative, "datasets": minimum_datasets},
        "statement": (
            "Eligible for a bounded product-quality claim on this exact test split and configuration."
            if bool(rows) and all(checks.values())
            else "Regression evidence only; not eligible for product accuracy or paper-level claims."
        ),
    }


def reproducibility_metadata(
    *,
    config: dict[str, Any],
    dataset: dict[str, Any],
    runtime_backend: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = source_revision()
    source_hashes = {
        str(path.relative_to(ROOT)): file_sha256(path)
        for path in ALGORITHM_SOURCE_FILES
        if path.exists()
    }
    model_files = {}
    for key in ("yolo_model", "hailo_pose_model", "hailo_object_model"):
        configured = str(config.get(key) or "")
        model_path = resolve_model_path(configured)
        model_files[key] = {
            "configured_path": configured,
            "resolved_path": str(model_path) if model_path else None,
            "sha256": file_sha256(model_path) if model_path else None,
        }
    return {
        "source": source,
        "source_files": source_hashes,
        "source_fingerprint": canonical_hash(source_hashes),
        "models": model_files,
        "runtime_backend": runtime_backend or {},
        "config_fingerprint": canonical_hash(config),
        "dataset": dataset,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
        },
        "command": sys.argv,
    }


def resolve_model_path(raw: str) -> Path | None:
    if not raw:
        return None
    candidates = [Path(raw), ROOT / raw, ROOT / "models" / raw]
    return next((path.resolve() for path in candidates if path.exists() and path.is_file()), None)


def source_revision() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}


def latency_metrics(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"p50_ms": None, "p95_ms": None, "max_ms": None}
    values = sorted(values)
    p50 = values[int((len(values) - 1) * 0.50)]
    p95 = values[int((len(values) - 1) * 0.95)]
    return {"p50_ms": p50, "p95_ms": p95, "max_ms": values[-1]}


def write_report(task: str, report: dict[str, Any], report_path: Path | None) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = report_path or REPORT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = {
        "ok": report["metrics"]["errors"] == 0,
        "task": report["task"],
        "count": report["count"],
        "metrics": report["metrics"],
        "quality_claim_ready": report["quality_claim"]["ready"],
        "latency": report["latency"],
        "report": str(path),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
