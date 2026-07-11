from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "eval"
REPOSITORY = "ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos"
BASE_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/master"
LICENSE_NOTE = "MIT; cite GMDCSA24 and DOI 10.5281/zenodo.12921216."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a curated GMDCSA24 fall/ADL sample set.")
    parser.add_argument("--subject", type=int, default=1, choices=[1, 2, 3, 4])
    parser.add_argument("--fall", nargs="*", default=["01", "05", "11", "15"])
    parser.add_argument("--adl", nargs="*", default=["01", "03", "07", "08", "15"])
    parser.add_argument("--raw-dir", type=Path, default=DATA_ROOT / "raw" / "gmdcsa24")
    parser.add_argument("--samples-dir", type=Path, default=DATA_ROOT / "samples" / "fall" / "gmdcsa24")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument(
        "--temporal-samples",
        type=int,
        default=0,
        help="When greater than zero, sample this many ordered frames per video for temporal evaluation.",
    )
    return parser.parse_args()


def normalize_ids(values: list[str]) -> list[str]:
    return [part.strip().zfill(2) for value in values for part in value.split(",") if part.strip()]


def download_file(url: str, target: Path, args: argparse.Namespace) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0 and not args.force:
        return
    if args.no_download:
        raise FileNotFoundError(f"missing local file: {target}")
    temporary = target.with_suffix(target.suffix + ".tmp")
    last_error: Exception | None = None
    for attempt in range(max(1, args.retries + 1)):
        try:
            request = Request(url, headers={"User-Agent": "GoHomeVisionEval/1.0"})
            with urlopen(request, timeout=args.timeout) as response, temporary.open("wb") as handle:
                while chunk := response.read(1024 * 256):
                    handle.write(chunk)
            temporary.replace(target)
            return
        except (OSError, URLError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < args.retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {last_error}") from last_error


def source_url(subject: int, category: str, filename: str) -> str:
    path = f"Subject {subject}/{category}/{filename}"
    return f"{BASE_URL}/{quote(path, safe='/')}"


def load_catalog(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            filename = str(row.get("File Name") or "").strip()
            if filename:
                rows[filename] = {str(key): str(value or "") for key, value in row.items() if key}
    return rows


def fall_interval(row: dict[str, str]) -> tuple[float, float]:
    text = " ".join(row.values())
    match = re.search(r"Falling[^\[]*\[\s*([0-9.]+)\s*to\s*([0-9.]+)\s*\]", text, re.IGNORECASE)
    if not match:
        duration = float(row.get("Length (seconds)") or 5)
        return duration * 0.45, duration
    return float(match.group(1)), float(match.group(2))


def frame_at(video_path: Path, seconds: float) -> tuple[Any, int]:
    import cv2  # type: ignore

    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"cannot open video: {video_path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, seconds) * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"cannot read {seconds:.2f}s from {video_path}")
        return frame, int(round(seconds * fps))
    finally:
        capture.release()


def write_sample(video_path: Path, target: Path, seconds: float, force: bool) -> int:
    import cv2  # type: ignore

    if target.exists() and target.stat().st_size > 0 and not force:
        capture = cv2.VideoCapture(str(video_path))
        try:
            return int(round(seconds * float(capture.get(cv2.CAP_PROP_FPS) or 25.0)))
        finally:
            capture.release()
    frame, frame_index = frame_at(video_path, seconds)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
        raise RuntimeError(f"cannot write frame: {target}")
    return frame_index


def temporal_times(duration: float, sample_count: int) -> list[float]:
    count = max(2, int(sample_count))
    start = min(0.15, max(0.0, duration * 0.02))
    end = max(start, duration - min(0.15, duration * 0.02))
    if end <= start:
        return [max(0.0, duration * index / max(1, count - 1)) for index in range(count)]
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


def entry(
    *,
    target: Path,
    samples_dir: Path,
    expected: bool,
    subject: int,
    category: str,
    filename: str,
    seconds: float,
    frame_index: int,
    description: str,
) -> dict[str, Any]:
    return {
        "file": str(target.relative_to(samples_dir)),
        "fall": expected,
        "source_dataset": "GMDCSA24",
        "source_url": source_url(subject, category, filename),
        "source_repository": f"https://github.com/{REPOSITORY}",
        "license": LICENSE_NOTE,
        "subject": subject,
        "category": category.lower(),
        "sequence_id": Path(filename).stem,
        "timestamp_seconds": round(seconds, 3),
        "frame_index": frame_index,
        "description": description,
        "config": {
            "pose_detection_enabled": True,
            "person_detection_enabled": True,
            "fall_detection_enabled": True,
        },
    }


def main() -> None:
    args = parse_args()
    subject = args.subject
    falls = normalize_ids(args.fall)
    adls = normalize_ids(args.adl)
    raw_root = args.raw_dir.resolve() / f"subject-{subject}"
    samples_dir = args.samples_dir.resolve() / f"subject-{subject}"
    raw_root.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    catalogs: dict[str, dict[str, dict[str, str]]] = {}
    for category in ("Fall", "ADL"):
        catalog_path = raw_root / f"{category}.csv"
        download_file(f"{BASE_URL}/{quote(f'Subject {subject}/{category}.csv', safe='/')}", catalog_path, args)
        catalogs[category] = load_catalog(catalog_path)

    entries: list[dict[str, Any]] = []
    for sequence_id in falls:
        filename = f"{sequence_id}.mp4"
        row = catalogs["Fall"].get(filename)
        if row is None:
            raise RuntimeError(f"missing Fall catalog row: {filename}")
        video_path = raw_root / "Fall" / filename
        download_file(source_url(subject, "Fall", filename), video_path, args)
        start, end = fall_interval(row)
        duration = float(row.get("Length (seconds)") or max(end, 5))
        if args.temporal_samples > 0:
            times = [
                (
                    seconds,
                    seconds >= start,
                    "pre_fall" if seconds < start else ("falling" if seconds < end else "fallen"),
                )
                for seconds in temporal_times(duration, args.temporal_samples)
            ]
        else:
            times = [(max(0.15, start * 0.45), False, "pre_fall"), (start + (end - start) * 0.58, True, "fallen"), (max(start, end - 0.18), True, "fallen_end")]
        for index, (seconds, expected, note) in enumerate(times):
            profile = "dense-" if args.temporal_samples > 0 else ""
            target = samples_dir / f"fall-{sequence_id}-{profile}{index + 1:02d}-{'pos' if expected else 'neg'}.jpg"
            frame_index = write_sample(video_path, target, seconds, args.force)
            entries.append(entry(target=target, samples_dir=args.samples_dir.resolve(), expected=expected, subject=subject, category="Fall", filename=filename, seconds=seconds, frame_index=frame_index, description=f"{note}: {row.get('Description', '')}"))

    for sequence_id in adls:
        filename = f"{sequence_id}.mp4"
        row = catalogs["ADL"].get(filename)
        if row is None:
            raise RuntimeError(f"missing ADL catalog row: {filename}")
        video_path = raw_root / "ADL" / filename
        download_file(source_url(subject, "ADL", filename), video_path, args)
        duration = float(row.get("Length (seconds)") or 5)
        times = temporal_times(duration, args.temporal_samples) if args.temporal_samples > 0 else (duration * 0.45, max(0.2, duration - 0.25))
        for index, seconds in enumerate(times):
            profile = "dense-" if args.temporal_samples > 0 else ""
            target = samples_dir / f"adl-{sequence_id}-{profile}{index + 1:02d}-neg.jpg"
            frame_index = write_sample(video_path, target, seconds, args.force)
            entries.append(entry(target=target, samples_dir=args.samples_dir.resolve(), expected=False, subject=subject, category="ADL", filename=filename, seconds=seconds, frame_index=frame_index, description=row.get("Description", "")))

    manifest = args.samples_dir.resolve() / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")
    print(json.dumps({"ok": True, "dataset": "GMDCSA24", "subject": subject, "count": len(entries), "positives": sum(1 for item in entries if item["fall"]), "negatives": sum(1 for item in entries if not item["fall"]), "manifest": str(manifest)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
