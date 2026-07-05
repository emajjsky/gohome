from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "eval"
DEFAULT_BASE_URL = "https://fenix.ur.edu.pl/~mkepski/ds/data"
LICENSE_NOTE = "CC BY-NC-SA 4.0; research validation only, contact dataset owner for commercial use."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a small, labeled UR Fall sample set for GoHome fall evaluation."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--fall", nargs="*", default=["01", "02"], help="Fall sequence numbers, e.g. 01 02.")
    parser.add_argument("--adl", nargs="*", default=["01", "02"], help="ADL sequence numbers, e.g. 01 02.")
    parser.add_argument("--raw-dir", type=Path, default=DATA_ROOT / "raw" / "ur_fall")
    parser.add_argument("--samples-dir", type=Path, default=DATA_ROOT / "samples" / "fall" / "ur_fall")
    parser.add_argument("--camera", default="cam0", choices=["cam0"], help="UR Fall extracted labels are cam0/front.")
    parser.add_argument("--positive-per-fall", type=int, default=4)
    parser.add_argument("--negative-per-fall", type=int, default=2)
    parser.add_argument("--negative-per-adl", type=int, default=4)
    parser.add_argument(
        "--crop",
        default="rgb-right",
        choices=["rgb-right", "none"],
        help="UR Fall MP4 preview is depth+RGB; default keeps the right RGB half only.",
    )
    parser.add_argument("--include-transition", action="store_true", help="Treat label 0 falling-transition frames as positive.")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true", help="Re-download and overwrite extracted frames.")
    parser.add_argument("--no-download", action="store_true", help="Use existing files only.")
    return parser.parse_args()


def normalize_ids(values: list[str]) -> list[str]:
    ids: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            ids.append(part.zfill(2))
    return ids


def download_file(url: str, target: Path, *, timeout: int, retries: int, force: bool, no_download: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0 and not force:
        return
    if no_download:
        if target.exists() and target.stat().st_size > 0:
            return
        raise FileNotFoundError(f"missing local file and --no-download is set: {target}")

    tmp = target.with_suffix(target.suffix + ".tmp")
    last_error: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            request = Request(url, headers={"User-Agent": "GoHomeVisionEval/1.0"})
            with urlopen(request, timeout=timeout) as response, tmp.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    handle.write(chunk)
            tmp.replace(target)
            return
        except (OSError, URLError) as exc:
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {last_error}") from last_error


def download_urfall_assets(args: argparse.Namespace, falls: list[str], adls: list[str]) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    base_url = str(args.base_url).rstrip("/")
    csv_files = {
        "falls_csv": "urfall-cam0-falls.csv",
        "adls_csv": "urfall-cam0-adls.csv",
    }
    for key, filename in csv_files.items():
        target = args.raw_dir / filename
        download_file(
            f"{base_url}/{filename}",
            target,
            timeout=args.timeout,
            retries=args.retries,
            force=args.force,
            no_download=args.no_download,
        )
        assets[key] = target

    for sequence_id in falls:
        filename = f"fall-{sequence_id}-{args.camera}.mp4"
        target = args.raw_dir / filename
        download_file(
            f"{base_url}/{filename}",
            target,
            timeout=args.timeout,
            retries=args.retries,
            force=args.force,
            no_download=args.no_download,
        )
        assets[f"fall-{sequence_id}"] = target

    for sequence_id in adls:
        filename = f"adl-{sequence_id}-{args.camera}.mp4"
        target = args.raw_dir / filename
        download_file(
            f"{base_url}/{filename}",
            target,
            timeout=args.timeout,
            retries=args.retries,
            force=args.force,
            no_download=args.no_download,
        )
        assets[f"adl-{sequence_id}"] = target
    return assets


def load_labels(path: Path) -> dict[str, list[tuple[int, int]]]:
    labels: dict[str, list[tuple[int, int]]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 3:
                continue
            sequence_name = row[0].strip()
            try:
                frame_number = int(float(row[1]))
                label = int(float(row[2]))
            except ValueError:
                continue
            labels.setdefault(sequence_name, []).append((frame_number, label))
    for rows in labels.values():
        rows.sort(key=lambda item: item[0])
    return labels


def pick_evenly(values: list[int], limit: int) -> list[int]:
    if limit <= 0 or not values:
        return []
    if len(values) <= limit:
        return values
    if limit == 1:
        return [values[len(values) // 2]]
    picked: list[int] = []
    span = len(values) - 1
    for index in range(limit):
        picked.append(values[round(index * span / (limit - 1))])
    return sorted(set(picked))


def selected_frames_for_fall(
    rows: list[tuple[int, int]],
    *,
    positive_limit: int,
    negative_limit: int,
    include_transition: bool,
) -> list[tuple[int, bool, str]]:
    positive_labels = {1, 0} if include_transition else {1}
    positive = [frame for frame, label in rows if label in positive_labels]
    first_action_frame = min([frame for frame, label in rows if label in {0, 1}], default=None)
    if first_action_frame is None:
        negative = [frame for frame, label in rows if label == -1]
    else:
        negative = [frame for frame, label in rows if label == -1 and frame < first_action_frame]
    selected: list[tuple[int, bool, str]] = []
    selected.extend((frame, False, "pre_fall_not_lying") for frame in pick_evenly(negative, negative_limit))
    selected.extend((frame, True, "lying_on_ground") for frame in pick_evenly(positive, positive_limit))
    return sorted(selected, key=lambda item: item[0])


def selected_frames_for_adl(rows: list[tuple[int, int]], *, negative_limit: int) -> list[tuple[int, bool, str]]:
    negative = [frame for frame, label in rows if label == -1]
    return [(frame, False, "adl_not_lying") for frame in pick_evenly(negative, negative_limit)]


def read_frame(video_path: Path, frame_number: int) -> Any | None:
    import cv2  # type: ignore

    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return None
        target_index = max(0, frame_number - 1)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count:
            target_index = min(target_index, max(0, frame_count - 1))
        for offset in [0, -1, 1, -2, 2, -4, 4]:
            index = max(0, target_index + offset)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = cap.read()
            if ok and frame is not None:
                return frame
    finally:
        cap.release()
    return None


def crop_frame(frame: Any, mode: str) -> Any:
    if mode == "none":
        return frame
    if mode == "rgb-right":
        width = int(frame.shape[1])
        if width >= 2:
            return frame[:, width // 2 :]
    return frame


def write_frame(video_path: Path, output_path: Path, frame_number: int, *, crop: str, jpeg_quality: int = 92) -> None:
    import cv2  # type: ignore

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = read_frame(video_path, frame_number)
    if frame is None:
        raise RuntimeError(f"cannot read frame {frame_number} from {video_path}")
    frame = crop_frame(frame, crop)
    ok = cv2.imwrite(str(output_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError(f"cannot write frame: {output_path}")


def make_entry(
    *,
    file_path: Path,
    samples_dir: Path,
    expected: bool,
    sequence_name: str,
    sequence_kind: str,
    frame_number: int,
    source_video: Path,
    source_features: Path,
    label_note: str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "file": str(file_path.relative_to(samples_dir)),
        "fall": expected,
        "label": expected,
        "source_dataset": "UR Fall Detection Dataset",
        "source_url": source_url,
        "license": LICENSE_NOTE,
        "sequence_id": sequence_name,
        "sequence_kind": sequence_kind,
        "frame_number": frame_number,
        "frame_index": max(0, frame_number - 1),
        "crop": "right_rgb_half",
        "source_video": str(source_video),
        "source_features": str(source_features),
        "label_note": label_note,
        "config": {
            "pose_detection_enabled": True,
            "fall_detection_enabled": True,
            "person_detection_enabled": True,
        },
    }


def write_readme(samples_dir: Path) -> None:
    readme = samples_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# UR Fall curated sample",
                "",
                "Small local sample set generated by `scripts/import-ur-fall-sample.py`.",
                "",
                "- Positive frames use UR Fall label `1`: person lying on the ground.",
                "- Negative frames use UR Fall label `-1`: person not lying.",
                "- Transition frames `0` are skipped by default because the dataset authors did not use them for classification.",
                f"- License: {LICENSE_NOTE}",
                "",
                "Run:",
                "",
                "```bash",
                "python scripts/eval-fall.py --use-pose --samples-dir data/eval/samples/fall/ur_fall",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    falls = normalize_ids(args.fall)
    adls = normalize_ids(args.adl)
    args.raw_dir = args.raw_dir.resolve()
    args.samples_dir = args.samples_dir.resolve()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.samples_dir.mkdir(parents=True, exist_ok=True)

    assets = download_urfall_assets(args, falls, adls)
    fall_labels = load_labels(assets["falls_csv"])
    adl_labels = load_labels(assets["adls_csv"])

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    base_url = str(args.base_url).rstrip("/")
    for sequence_id in falls:
        sequence_name = f"fall-{sequence_id}"
        rows = fall_labels.get(sequence_name, [])
        video_path = assets[sequence_name]
        if not rows:
            errors.append(f"missing labels for {sequence_name}")
            continue
        for frame_number, expected, label_note in selected_frames_for_fall(
            rows,
            positive_limit=args.positive_per_fall,
            negative_limit=args.negative_per_fall,
            include_transition=args.include_transition,
        ):
            polarity = "pos" if expected else "neg"
            output = args.samples_dir / f"{sequence_name}_{args.camera}_f{frame_number:05d}_{polarity}.jpg"
            if args.force or not output.exists():
                write_frame(video_path, output, frame_number, crop=args.crop)
            entries.append(
                make_entry(
                    file_path=output,
                    samples_dir=args.samples_dir,
                    expected=expected,
                    sequence_name=sequence_name,
                    sequence_kind="fall",
                    frame_number=frame_number,
                    source_video=video_path,
                    source_features=assets["falls_csv"],
                    label_note=label_note,
                    source_url=f"{base_url}/{video_path.name}",
                )
            )

    for sequence_id in adls:
        sequence_name = f"adl-{sequence_id}"
        rows = adl_labels.get(sequence_name, [])
        video_path = assets[sequence_name]
        if not rows:
            errors.append(f"missing labels for {sequence_name}")
            continue
        for frame_number, expected, label_note in selected_frames_for_adl(
            rows,
            negative_limit=args.negative_per_adl,
        ):
            output = args.samples_dir / f"{sequence_name}_{args.camera}_f{frame_number:05d}_neg.jpg"
            if args.force or not output.exists():
                write_frame(video_path, output, frame_number, crop=args.crop)
            entries.append(
                make_entry(
                    file_path=output,
                    samples_dir=args.samples_dir,
                    expected=expected,
                    sequence_name=sequence_name,
                    sequence_kind="adl",
                    frame_number=frame_number,
                    source_video=video_path,
                    source_features=assets["adls_csv"],
                    label_note=label_note,
                    source_url=f"{base_url}/{video_path.name}",
                )
            )

    manifest_path = args.samples_dir / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
        encoding="utf-8",
    )
    write_readme(args.samples_dir)
    positives = sum(1 for entry in entries if entry["fall"])
    negatives = len(entries) - positives
    print(
        json.dumps(
            {
                "ok": not errors,
                "dataset": "ur_fall",
                "raw_dir": str(args.raw_dir),
                "samples_dir": str(args.samples_dir),
                "manifest": str(manifest_path),
                "fall_sequences": falls,
                "adl_sequences": adls,
                "samples": len(entries),
                "positive": positives,
                "negative": negatives,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
