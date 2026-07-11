#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES_DIR = ROOT / "data" / "eval" / "samples"
DEFAULT_REPORT_DIR = ROOT / "data" / "eval" / "reports"
POSE_LABELS = {"standing", "sitting", "squatting", "bending", "lying", "upper_body"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit GoHome vision dataset coverage without training a model.")
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--require-fall-regression", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def task_for_manifest(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    for task in ("fall", "fire", "person", "pose", "activity"):
        if task in parts:
            return task
    return "other"


def bool_label(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "positive", "pos"}


def sequence_key(entry: dict[str, Any]) -> str | None:
    sequence_id = entry.get("sequence_id") or entry.get("source_video") or entry.get("clip_id")
    if sequence_id in (None, ""):
        return None
    return "|".join([
        str(entry.get("source_dataset") or entry.get("dataset") or "local"),
        str(entry.get("subject") or entry.get("family_id") or ""),
        str(entry.get("category") or entry.get("sequence_kind") or "sequence"),
        str(sequence_id),
    ])


def audit(samples_dir: Path) -> dict[str, Any]:
    samples_dir = samples_dir.resolve()
    manifests = sorted(samples_dir.rglob("manifest.jsonl")) if samples_dir.exists() else []
    task_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manifest_summaries = []
    missing_files = []

    for manifest in manifests:
        rows = load_jsonl(manifest)
        task = task_for_manifest(manifest.relative_to(samples_dir))
        task_rows[task].extend(rows)
        for row in rows:
            file_name = str(row.get("file") or "").strip()
            if file_name and not (manifest.parent / file_name).exists():
                missing_files.append(str((manifest.parent / file_name).relative_to(samples_dir)))
        manifest_summaries.append({
            "path": str(manifest.relative_to(samples_dir)),
            "task": task,
            "row_count": len(rows),
        })

    fall_sequences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows["fall"]:
        key = sequence_key(row)
        if key:
            fall_sequences[key].append(row)
    fall_positive_sequences = sum(
        1 for rows in fall_sequences.values()
        if any(bool_label(row.get("fall", row.get("label"))) for row in rows)
    )
    fall_negative_sequences = len(fall_sequences) - fall_positive_sequences
    fall_datasets = {
        str(row.get("source_dataset") or row.get("dataset") or "local")
        for row in task_rows["fall"]
        if sequence_key(row)
    }
    home_negative_rows = [
        row for manifest in manifests
        if "home_false_positive" in manifest.parts
        for row in load_jsonl(manifest)
        if not bool_label(row.get("fall", row.get("label")))
    ]

    pose_counts = Counter(
        str(row.get("posture") or row.get("label") or "").strip()
        for row in task_rows["pose"]
        if str(row.get("posture") or row.get("label") or "").strip() in POSE_LABELS
    )
    pose_sequence_counts: dict[str, set[str]] = defaultdict(set)
    for row in task_rows["pose"]:
        label = str(row.get("posture") or row.get("label") or "").strip()
        key = sequence_key(row)
        if label in POSE_LABELS and key:
            pose_sequence_counts[label].add(key)

    fire_sequences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows["fire"]:
        key = sequence_key(row)
        if key:
            fire_sequences[key].append(row)
    fire_positive_sequences = sum(
        1 for rows in fire_sequences.values()
        if any(bool_label(row.get("fire_event", row.get("fire"))) for row in rows)
    )
    fire_negative_sequences = len(fire_sequences) - fire_positive_sequences

    split_sequences: dict[str, set[str]] = defaultdict(set)
    all_rows = [row for rows in task_rows.values() for row in rows]
    for row in all_rows:
        split = str(row.get("split") or "").strip().lower()
        key = sequence_key(row)
        if split and key:
            split_sequences[split].add(key)
    required_splits = {"train", "validation", "test"}
    split_names = set(split_sequences)
    leakage = []
    for left in split_sequences:
        for right in split_sequences:
            if left >= right:
                continue
            overlap = sorted(split_sequences[left] & split_sequences[right])
            if overlap:
                leakage.append({"splits": [left, right], "sequence_count": len(overlap), "sequences": overlap[:10]})

    gates = {
        "fall_rule_regression": {
            "ready": (
                len(fall_sequences) >= 20
                and fall_positive_sequences >= 8
                and fall_negative_sequences >= 10
                and len(fall_datasets) >= 2
            ),
            "purpose": "Prevent regressions in the current explainable fall state machine; not a product accuracy claim.",
            "observed": {
                "sequence_count": len(fall_sequences),
                "positive_sequences": fall_positive_sequences,
                "negative_sequences": fall_negative_sequences,
                "dataset_count": len(fall_datasets),
            },
            "minimum": {
                "sequence_count": 20,
                "positive_sequences": 8,
                "negative_sequences": 10,
                "dataset_count": 2,
            },
        },
        "home_false_positive_pilot": {
            "ready": len(home_negative_rows) >= 50,
            "purpose": "Pilot false-positive validation for the real camera viewpoints and home environment.",
            "observed": {"negative_images": len(home_negative_rows)},
            "minimum": {"negative_images": 50},
        },
        "posture_episode_evaluation": {
            "ready": all(len(pose_sequence_counts[label]) >= 10 for label in POSE_LABELS),
            "purpose": "Evaluate posture episode labels and transition boundaries by complete sequence.",
            "observed": {label: len(pose_sequence_counts[label]) for label in sorted(POSE_LABELS)},
            "minimum": {"sequences_per_label": 10},
        },
        "fire_temporal_evaluation": {
            "ready": fire_positive_sequences >= 10 and fire_negative_sequences >= 10,
            "purpose": "Evaluate temporal fire/smoke candidates instead of single-frame warm-color heuristics.",
            "observed": {
                "positive_sequences": fire_positive_sequences,
                "negative_sequences": fire_negative_sequences,
                "single_frame_rows": len(task_rows["fire"]),
            },
            "minimum": {"positive_sequences": 10, "negative_sequences": 10},
        },
        "trainable_temporal_model": {
            "ready": required_splits.issubset(split_names) and not leakage and all(
                len(pose_sequence_counts[label]) >= 10 for label in POSE_LABELS
            ),
            "purpose": "Start model experiments only after sequence-disjoint splits and posture sequence labels exist.",
            "observed": {
                "splits": sorted(split_names),
                "split_leakage": leakage,
                "pose_frame_labels": dict(sorted(pose_counts.items())),
            },
            "required": {
                "splits": sorted(required_splits),
                "sequence_disjoint": True,
                "posture_sequence_coverage": True,
            },
        },
    }

    return {
        "schema_version": "gohome-vision-dataset-readiness-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "samples_dir": str(samples_dir),
        "manifest_count": len(manifests),
        "manifest_rows": sum(len(rows) for rows in task_rows.values()),
        "image_count": sum(1 for path in samples_dir.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"}),
        "missing_files": missing_files,
        "manifests": manifest_summaries,
        "coverage": {
            "fall": {
                "frame_rows": len(task_rows["fall"]),
                "sequence_count": len(fall_sequences),
                "positive_sequences": fall_positive_sequences,
                "negative_sequences": fall_negative_sequences,
                "datasets": sorted(fall_datasets),
                "home_negative_images": len(home_negative_rows),
            },
            "pose": {
                "rows": len(task_rows["pose"]),
                "frame_labels": dict(sorted(pose_counts.items())),
                "sequence_labels": {label: len(pose_sequence_counts[label]) for label in sorted(POSE_LABELS)},
            },
            "fire": {
                "rows": len(task_rows["fire"]),
                "sequence_count": len(fire_sequences),
                "positive_sequences": fire_positive_sequences,
                "negative_sequences": fire_negative_sequences,
            },
            "person": {"rows": len(task_rows["person"])},
        },
        "splits": {
            "names": sorted(split_names),
            "sequence_counts": {key: len(value) for key, value in sorted(split_sequences.items())},
            "leakage": leakage,
        },
        "gates": gates,
        "conclusion": {
            "current_rules": "sufficient_for_fall_regression" if gates["fall_rule_regression"]["ready"] else "insufficient",
            "product_validation": "insufficient" if not gates["home_false_positive_pilot"]["ready"] else "pilot_ready",
            "model_training": "insufficient" if not gates["trainable_temporal_model"]["ready"] else "experiment_ready",
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
        "ok": not report["missing_files"],
        "report": str(report_path),
        "image_count": report["image_count"],
        "manifest_rows": report["manifest_rows"],
        "fall": report["coverage"]["fall"],
        "pose": report["coverage"]["pose"],
        "fire": report["coverage"]["fire"],
        "gates": {key: value["ready"] for key, value in report["gates"].items()},
        "conclusion": report["conclusion"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if report["missing_files"] or (args.require_fall_regression and not report["gates"]["fall_rule_regression"]["ready"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
