from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
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
    parser.add_argument("--detector-backend", default="basic", choices=["basic", "yolo"])
    parser.add_argument("--yolo-model", default="yolo11n.pt")
    parser.add_argument("--yolo-confidence", type=float, default=0.20)
    parser.add_argument("--yolo-imgsz", type=int, default=960)
    parser.add_argument("--pose-enabled", action="store_true")
    parser.add_argument("--pose-mode", default="lightweight")
    parser.add_argument("--pose-device", default="cpu")
    parser.add_argument("--pose-det-frequency", type=int, default=1)
    parser.add_argument("--max-video-frames", type=int, default=120)
    parser.add_argument("--video-stride", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
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
    )


def load_manifest(path: Path | None, samples_dir: Path) -> list[dict[str, Any]]:
    manifest_path = path
    if manifest_path is None:
        for candidate in [samples_dir / "manifest.jsonl", samples_dir / "manifest.json"]:
            if candidate.exists():
                manifest_path = candidate
                break
    if manifest_path is None or not manifest_path.exists():
        return [{"file": str(path.relative_to(samples_dir))} for path in discover_media(samples_dir)]
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


def iter_samples(entries: list[dict[str, Any]], samples_dir: Path, *, max_video_frames: int, video_stride: int) -> Iterable[EvalSample]:
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
    entries = load_manifest(args.manifest, args.samples_dir)
    if args.limit:
        entries = entries[: max(1, int(args.limit))]
    agent = make_agent(args)
    rows: list[dict[str, Any]] = []
    metrics = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "unlabeled": 0, "errors": 0}
    latencies: list[int] = []
    for sample in iter_samples(
        entries,
        args.samples_dir,
        max_video_frames=int(args.max_video_frames),
        video_stride=int(args.video_stride),
    ):
        result, error, elapsed_ms = analyze_frame(agent, sample)
        expected = expected_bool(sample.entry, label_keys)
        predicted = bool(predict(result or {})) if result is not None else False
        if elapsed_ms >= 0:
            latencies.append(elapsed_ms)
        if result is None:
            metrics["errors"] += 1
        elif expected is None:
            metrics["unlabeled"] += 1
        elif predicted and expected:
            metrics["tp"] += 1
        elif predicted and not expected:
            metrics["fp"] += 1
        elif not predicted and expected:
            metrics["fn"] += 1
        else:
            metrics["tn"] += 1
        rows.append(
            {
                "file": str(sample.path),
                "frame_index": sample.frame_index,
                "timestamp_ms": sample.timestamp_ms,
                "expected": expected,
                "predicted": predicted,
                "latency_ms": elapsed_ms,
                "error": error,
                "detail": detail(result or {}),
            }
        )
    report = {
        "schema_version": "gohome-vision-eval-report-v1",
        "task": task,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "samples_dir": str(args.samples_dir),
        "count": len(rows),
        "metrics": {**metrics, **rate_metrics(metrics)},
        "latency": latency_metrics(latencies),
        "config": {
            "detector_backend": args.detector_backend,
            "yolo_model": args.yolo_model,
            "yolo_confidence": args.yolo_confidence,
            "yolo_imgsz": args.yolo_imgsz,
            "pose_enabled": bool(args.pose_enabled),
            "pose_mode": args.pose_mode,
            "pose_device": args.pose_device,
            "pose_det_frequency": args.pose_det_frequency,
        },
        "rows": rows,
    }
    write_report(task, report, args.report)
    return report


def rate_metrics(metrics: dict[str, int]) -> dict[str, float | None]:
    tp = metrics["tp"]
    fp = metrics["fp"]
    tn = metrics["tn"]
    fn = metrics["fn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    false_positive_rate = fp / (fp + tn) if fp + tn else None
    return {
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
    }


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
        "ok": True,
        "task": report["task"],
        "count": report["count"],
        "metrics": report["metrics"],
        "latency": report["latency"],
        "report": str(path),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
