#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from eval_vision_common import (
    audit_split_integrity,
    classification_metrics,
    dataset_metadata,
    quality_claim_gate,
    stratified_metrics,
)


def metric_rows() -> list[dict]:
    return [
        {"file": "tp", "expected": True, "predicted": True, "error": "", "dataset": "A", "category": "fall"},
        {"file": "fn", "expected": True, "predicted": False, "error": "", "dataset": "A", "category": "fall"},
        {"file": "tn", "expected": False, "predicted": False, "error": "", "dataset": "B", "category": "adl"},
        {"file": "fp", "expected": False, "predicted": True, "error": "", "dataset": "B", "category": "adl"},
        {"file": "unlabeled", "expected": None, "predicted": False, "error": "", "dataset": "B", "category": "adl"},
        {"file": "error", "expected": True, "predicted": False, "error": "read_failed", "dataset": "B", "category": "fall"},
    ]


def split_entries() -> list[dict]:
    return [
        {"file": "train.jpg", "split": "train", "source_dataset": "A", "subject": "s1", "sequence_id": "q1"},
        {"file": "validation.jpg", "split": "validation", "source_dataset": "A", "subject": "s2", "sequence_id": "q2"},
        {"file": "test-a.jpg", "split": "test", "source_dataset": "A", "subject": "s3", "sequence_id": "q3"},
        {"file": "test-b.jpg", "split": "test", "source_dataset": "B", "subject": "s4", "sequence_id": "q4"},
        {"file": "test-c.jpg", "split": "test", "source_dataset": "C", "subject": "s5", "sequence_id": "q5"},
    ]


def main() -> None:
    metrics = classification_metrics(metric_rows())
    assert metrics["tp"] == 1 and metrics["fp"] == 1 and metrics["tn"] == 1 and metrics["fn"] == 1
    assert metrics["errors"] == 1 and metrics["unlabeled"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["specificity"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["accuracy"] == 0.5
    assert metrics["balanced_accuracy"] == 0.5
    assert metrics["confidence_intervals_95"]["recall"]["low"] < 0.5
    assert stratified_metrics(metric_rows())["dataset"]["A"]["support"]["positive"] == 2

    clean_integrity = audit_split_integrity(split_entries())
    assert clean_integrity["required_splits_present"] is True
    assert clean_integrity["sequence_disjoint"] is True
    assert clean_integrity["subject_disjoint"] is True

    leaked = split_entries() + [
        {"file": "leak.jpg", "split": "test", "source_dataset": "A", "subject": "s1", "sequence_id": "q1"},
    ]
    leaked_integrity = audit_split_integrity(leaked)
    assert leaked_integrity["sequence_disjoint"] is False
    assert leaked_integrity["subject_disjoint"] is False

    claim_rows = [
        {"expected": True, "predicted": True, "error": "", "split": "test", "dataset": ["A", "B", "C"][index % 3]}
        for index in range(30)
    ] + [
        {"expected": False, "predicted": False, "error": "", "split": "test", "dataset": ["A", "B", "C"][index % 3]}
        for index in range(50)
    ]
    claim = quality_claim_gate(
        metrics=classification_metrics(claim_rows),
        rows=claim_rows,
        requested_split="test",
        split_integrity=clean_integrity,
        dataset_fingerprint="sha256",
        minimum_positive=30,
        minimum_negative=50,
        minimum_datasets=3,
    )
    assert claim["ready"] is True
    assert quality_claim_gate(
        metrics=classification_metrics(claim_rows),
        rows=claim_rows,
        requested_split="",
        split_integrity=clean_integrity,
        dataset_fingerprint="sha256",
        minimum_positive=30,
        minimum_negative=50,
        minimum_datasets=3,
    )["ready"] is False
    assert quality_claim_gate(
        metrics=classification_metrics(claim_rows),
        rows=claim_rows,
        requested_split="test",
        split_integrity=leaked_integrity,
        dataset_fingerprint="sha256",
        minimum_positive=30,
        minimum_negative=50,
        minimum_datasets=3,
    )["ready"] is False
    assert quality_claim_gate(
        metrics=classification_metrics(claim_rows),
        rows=claim_rows,
        requested_split="test",
        split_integrity=clean_integrity,
        dataset_fingerprint="sha256",
        minimum_positive=30,
        minimum_negative=50,
        minimum_datasets=3,
        sequence_evaluation=False,
    )["ready"] is False

    with tempfile.TemporaryDirectory(prefix="gohome-eval-fingerprint-a-") as first_dir, tempfile.TemporaryDirectory(
        prefix="gohome-eval-fingerprint-b-"
    ) as second_dir:
        entries = [{"file": "sample.jpg", "fall": True, "sequence_id": "sample-1"}]
        first = Path(first_dir)
        second = Path(second_dir)
        (first / "sample.jpg").write_bytes(b"same-content")
        (second / "sample.jpg").write_bytes(b"same-content")
        first_fingerprint = dataset_metadata(first, entries, None)["fingerprint"]
        second_fingerprint = dataset_metadata(second, entries, None)["fingerprint"]
        assert first_fingerprint == second_fingerprint
        (second / "sample.jpg").write_bytes(b"changed-content")
        assert dataset_metadata(second, entries, None)["fingerprint"] != first_fingerprint

    print(json.dumps({"ok": True, "metrics_schema": "v2", "quality_gate": "strict"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
