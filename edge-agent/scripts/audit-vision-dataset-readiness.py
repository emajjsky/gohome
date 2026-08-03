#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES_DIR = ROOT / "data" / "eval" / "samples"
DEFAULT_REPORT_DIR = ROOT / "data" / "eval" / "reports"
POSE_LABELS = {"standing", "sitting", "squatting", "bending", "lying", "upper_body"}
REQUIRED_SPLITS = {"train", "validation", "test"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit GoHome vision dataset coverage and split integrity.")
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--require-fall-regression", action="store_true")
    parser.add_argument("--require-product-quality-claim", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def task_for_manifest(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    for task in ("fall", "person", "pose", "activity"):
        if task in parts:
            return task
    return "other"


def bool_label(value: Any) -> bool | None:
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


def sequence_identity(entry: dict[str, Any]) -> str | None:
    sequence_id = entry.get("sequence_id") or entry.get("source_video") or entry.get("clip_id")
    if sequence_id in (None, ""):
        return None
    return "|".join([
        str(entry.get("source_dataset") or entry.get("dataset") or "local"),
        str(entry.get("subject") or entry.get("family_id") or ""),
        str(sequence_id),
    ])


def subject_identity(entry: dict[str, Any]) -> str | None:
    subject = entry.get("subject") or entry.get("family_id")
    if subject in (None, ""):
        return None
    return "|".join([
        str(entry.get("source_dataset") or entry.get("dataset") or "local"),
        str(subject),
    ])


def sequence_order(entry: dict[str, Any]) -> float | None:
    for key in ("timestamp_seconds", "frame_number", "frame_index"):
        if entry.get(key) is not None:
            try:
                return float(entry[key])
            except (TypeError, ValueError):
                return None
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pairwise_overlap(values: dict[str, set[str]]) -> list[dict[str, Any]]:
    overlaps = []
    names = sorted(values)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            shared = sorted(values[left] & values[right])
            if shared:
                overlaps.append({"splits": [left, right], "count": len(shared), "values": shared})
    return overlaps


def audit(samples_dir: Path) -> dict[str, Any]:
    samples_dir = samples_dir.resolve()
    manifests = sorted(samples_dir.rglob("manifest.jsonl")) if samples_dir.exists() else []
    task_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manifest_summaries = []
    missing_files = []
    unreadable_files = []
    indexed_rows = []

    for manifest in manifests:
        rows = load_jsonl(manifest)
        task = task_for_manifest(manifest.relative_to(samples_dir))
        task_rows[task].extend(rows)
        for row_index, row in enumerate(rows, start=1):
            file_name = str(row.get("file") or "").strip()
            path = manifest.parent / file_name if file_name else None
            relative_path = str(path.relative_to(samples_dir)) if path else ""
            content_hash = None
            if not file_name or path is None or not path.exists():
                missing_files.append(relative_path or f"{manifest.relative_to(samples_dir)}:{row_index}")
            elif not path.is_file():
                unreadable_files.append(relative_path)
            else:
                try:
                    content_hash = file_sha256(path)
                except OSError:
                    unreadable_files.append(relative_path)
            indexed_rows.append({
                "task": task,
                "manifest": str(manifest.relative_to(samples_dir)),
                "row_index": row_index,
                "relative_path": relative_path,
                "content_hash": content_hash,
                "entry": row,
            })
        manifest_summaries.append({
            "path": str(manifest.relative_to(samples_dir)),
            "task": task,
            "row_count": len(rows),
        })

    fall_rows = [item for item in indexed_rows if item["task"] == "fall"]
    fall_sequences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fall_rows_without_sequence = []
    fall_rows_without_label = []
    for item in fall_rows:
        entry = item["entry"]
        key = sequence_identity(entry)
        if key:
            fall_sequences[key].append(item)
        else:
            fall_rows_without_sequence.append(item["relative_path"])
        if bool_label(entry.get("fall", entry.get("label"))) is None:
            fall_rows_without_label.append(item["relative_path"])

    fall_sequence_labels: dict[str, bool | None] = {}
    sequence_order_issues = []
    sequence_metadata_issues = []
    for key, items in fall_sequences.items():
        labels = [bool_label(item["entry"].get("fall", item["entry"].get("label"))) for item in items]
        labeled = [label for label in labels if label is not None]
        fall_sequence_labels[key] = any(labeled) if labeled else None
        if len(items) > 1:
            orders = [sequence_order(item["entry"]) for item in items]
            if any(value is None for value in orders):
                sequence_order_issues.append({"sequence": key, "reason": "missing_or_invalid_order"})
            elif len(set(orders)) != len(orders):
                sequence_order_issues.append({"sequence": key, "reason": "duplicate_order"})
        for field in ("split", "source_dataset", "subject"):
            values = {str(item["entry"].get(field) or "").strip() for item in items}
            if len(values) > 1:
                sequence_metadata_issues.append({"sequence": key, "field": field, "values": sorted(values)})

    fall_positive_sequences = sum(label is True for label in fall_sequence_labels.values())
    fall_negative_sequences = sum(label is False for label in fall_sequence_labels.values())
    fall_unlabeled_sequences = sum(label is None for label in fall_sequence_labels.values())
    fall_datasets = {
        str(item["entry"].get("source_dataset") or item["entry"].get("dataset") or "local")
        for item in fall_rows
        if sequence_identity(item["entry"])
    }
    home_negative_rows = [
        item for item in fall_rows
        if "home_false_positive" in Path(item["manifest"]).parts
        and bool_label(item["entry"].get("fall", item["entry"].get("label"))) is False
    ]

    pose_counts = Counter(
        str(row.get("posture") or row.get("label") or "").strip()
        for row in task_rows["pose"]
        if str(row.get("posture") or row.get("label") or "").strip() in POSE_LABELS
    )
    pose_sequence_counts: dict[str, set[str]] = defaultdict(set)
    for row in task_rows["pose"]:
        label = str(row.get("posture") or row.get("label") or "").strip()
        key = sequence_identity(row)
        if label in POSE_LABELS and key:
            pose_sequence_counts[label].add(key)

    split_sequences: dict[str, set[str]] = defaultdict(set)
    split_subjects: dict[str, set[str]] = defaultdict(set)
    split_hashes: dict[str, set[str]] = defaultdict(set)
    split_names = set()
    rows_without_split = []
    for item in indexed_rows:
        entry = item["entry"]
        split = str(entry.get("split") or "").strip().lower()
        if not split:
            rows_without_split.append(item["relative_path"])
            continue
        split_names.add(split)
        sequence = sequence_identity(entry)
        subject = subject_identity(entry)
        if sequence:
            split_sequences[split].add(sequence)
        if subject:
            split_subjects[split].add(subject)
        if item["content_hash"]:
            split_hashes[split].add(item["content_hash"])

    sequence_leakage = pairwise_overlap(split_sequences)
    subject_leakage = pairwise_overlap(split_subjects)
    content_leakage = pairwise_overlap(split_hashes)
    duplicate_content: dict[str, list[str]] = defaultdict(list)
    for item in indexed_rows:
        if item["content_hash"]:
            duplicate_content[item["content_hash"]].append(item["relative_path"])
    duplicate_content_groups = [
        {"sha256": digest, "count": len(paths), "files": sorted(paths)}
        for digest, paths in sorted(duplicate_content.items())
        if len(paths) > 1
    ]

    test_sequence_labels = {
        key: label
        for key, label in fall_sequence_labels.items()
        if any(str(item["entry"].get("split") or "").strip().lower() == "test" for item in fall_sequences[key])
    }
    test_positive = sum(label is True for label in test_sequence_labels.values())
    test_negative = sum(label is False for label in test_sequence_labels.values())

    integrity_ready = not any([
        missing_files,
        unreadable_files,
        fall_rows_without_sequence,
        fall_rows_without_label,
        sequence_order_issues,
        sequence_metadata_issues,
        sequence_leakage,
        subject_leakage,
        content_leakage,
    ])
    posture_ready = all(len(pose_sequence_counts[label]) >= 10 for label in POSE_LABELS)
    gates = {
        "fall_rule_regression": {
            "ready": (
                len(fall_sequences) >= 20
                and fall_positive_sequences >= 8
                and fall_negative_sequences >= 10
                and len(fall_datasets) >= 2
                and not missing_files
                and fall_unlabeled_sequences == 0
                and not sequence_order_issues
            ),
            "purpose": "Prevent regressions in the explainable fall state machine; not a product accuracy claim.",
            "observed": {
                "sequence_count": len(fall_sequences),
                "positive_sequences": fall_positive_sequences,
                "negative_sequences": fall_negative_sequences,
                "unlabeled_sequences": fall_unlabeled_sequences,
                "dataset_count": len(fall_datasets),
            },
            "minimum": {
                "sequence_count": 20,
                "positive_sequences": 8,
                "negative_sequences": 10,
                "dataset_count": 2,
            },
        },
        "real_home_false_positive_pilot": {
            "ready": len(home_negative_rows) >= 50 and not missing_files,
            "purpose": "Pilot false-positive behavior on the actual home viewpoints; not a population accuracy claim.",
            "observed": {"negative_images": len(home_negative_rows)},
            "minimum": {"negative_images": 50},
        },
        "posture_episode_evaluation": {
            "ready": posture_ready,
            "purpose": "Evaluate complete posture episodes and transition boundaries instead of isolated images.",
            "observed": {label: len(pose_sequence_counts[label]) for label in sorted(POSE_LABELS)},
            "minimum": {"sequences_per_label": 10},
        },
        "temporal_model_experiment": {
            "ready": REQUIRED_SPLITS.issubset(split_names) and integrity_ready and posture_ready,
            "purpose": "Permit model experiments only after disjoint splits, complete labels and posture episodes exist.",
            "observed": {
                "splits": sorted(split_names),
                "sequence_leakage": sequence_leakage,
                "subject_leakage": subject_leakage,
                "content_leakage": content_leakage,
                "pose_frame_labels": dict(sorted(pose_counts.items())),
            },
            "required": {
                "splits": sorted(REQUIRED_SPLITS),
                "sequence_disjoint": True,
                "subject_disjoint": True,
                "content_disjoint": True,
                "posture_sequence_coverage": True,
            },
        },
        "product_quality_claim": {
            "ready": (
                REQUIRED_SPLITS.issubset(split_names)
                and integrity_ready
                and not rows_without_split
                and test_positive >= 30
                and test_negative >= 50
                and len(fall_datasets) >= 3
            ),
            "purpose": "Allow a bounded product-quality statement only on an independent, traceable test split.",
            "observed": {
                "test_positive_sequences": test_positive,
                "test_negative_sequences": test_negative,
                "dataset_count": len(fall_datasets),
                "rows_without_split": len(rows_without_split),
                "integrity_ready": integrity_ready,
            },
            "minimum": {
                "test_positive_sequences": 30,
                "test_negative_sequences": 50,
                "dataset_count": 3,
                "all_rows_split": True,
                "integrity_ready": True,
            },
        },
    }

    return {
        "schema_version": "gohome-vision-dataset-readiness-v2",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "samples_dir": str(samples_dir),
        "manifest_count": len(manifests),
        "manifest_rows": len(indexed_rows),
        "media_count": sum(
            1 for path in samples_dir.rglob("*")
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".mp4", ".mov", ".mkv"}
        ),
        "image_count": sum(1 for path in samples_dir.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"}),
        "missing_files": missing_files,
        "unreadable_files": unreadable_files,
        "manifests": manifest_summaries,
        "coverage": {
            "fall": {
                "frame_rows": len(fall_rows),
                "sequence_count": len(fall_sequences),
                "positive_sequences": fall_positive_sequences,
                "negative_sequences": fall_negative_sequences,
                "unlabeled_sequences": fall_unlabeled_sequences,
                "datasets": sorted(fall_datasets),
                "home_negative_images": len(home_negative_rows),
            },
            "pose": {
                "rows": len(task_rows["pose"]),
                "frame_labels": dict(sorted(pose_counts.items())),
                "sequence_labels": {label: len(pose_sequence_counts[label]) for label in sorted(POSE_LABELS)},
            },
            "person": {"rows": len(task_rows["person"])},
        },
        "data_quality": {
            "fall_rows_without_sequence": fall_rows_without_sequence,
            "fall_rows_without_label": fall_rows_without_label,
            "sequence_order_issues": sequence_order_issues,
            "sequence_metadata_issues": sequence_metadata_issues,
            "duplicate_content_groups": duplicate_content_groups,
        },
        "splits": {
            "names": sorted(split_names),
            "rows_without_split": rows_without_split,
            "sequence_counts": {key: len(value) for key, value in sorted(split_sequences.items())},
            "subject_counts": {key: len(value) for key, value in sorted(split_subjects.items())},
            "sequence_leakage": sequence_leakage,
            "subject_leakage": subject_leakage,
            "content_leakage": content_leakage,
        },
        "gates": gates,
        "conclusion": {
            "regression": "ready" if gates["fall_rule_regression"]["ready"] else "insufficient",
            "real_home_pilot": "ready" if gates["real_home_false_positive_pilot"]["ready"] else "insufficient",
            "model_experiment": "ready" if gates["temporal_model_experiment"]["ready"] else "insufficient",
            "product_quality_claim": "ready" if gates["product_quality_claim"]["ready"] else "insufficient",
        },
    }


def main() -> None:
    args = parse_args()
    report = audit(args.samples_dir)
    report_path = args.report
    if report_path is None:
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = DEFAULT_REPORT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_dataset_readiness.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "ok": not report["missing_files"] and not report["unreadable_files"],
        "report": str(report_path),
        "image_count": report["image_count"],
        "manifest_rows": report["manifest_rows"],
        "fall": report["coverage"]["fall"],
        "pose": report["coverage"]["pose"],
        "gates": {key: value["ready"] for key, value in report["gates"].items()},
        "conclusion": report["conclusion"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failed = report["missing_files"] or report["unreadable_files"]
    failed = failed or (args.require_fall_regression and not report["gates"]["fall_rule_regression"]["ready"])
    failed = failed or (args.require_product_quality_claim and not report["gates"]["product_quality_claim"]["ready"])
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
