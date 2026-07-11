#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


SCRIPT = Path(__file__).with_name("audit-vision-dataset-readiness.py")


def load_module():
    spec = importlib.util.spec_from_file_location("dataset_readiness_audit", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load dataset audit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (path.parent / row["file"]).write_bytes(b"fixture")
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def main() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="gohome-dataset-audit-") as temp_dir:
        root = Path(temp_dir)
        write_manifest(root / "fall" / "manifest.jsonl", [
            {"file": "fall-a-1.jpg", "fall": False, "source_dataset": "A", "sequence_id": "fall-a", "sequence_kind": "fall"},
            {"file": "fall-a-2.jpg", "fall": True, "source_dataset": "A", "sequence_id": "fall-a", "sequence_kind": "fall"},
            {"file": "adl-a.jpg", "fall": False, "source_dataset": "A", "sequence_id": "adl-a", "sequence_kind": "adl"},
        ])
        write_manifest(root / "pose" / "manifest.jsonl", [
            {"file": "stand.jpg", "posture": "standing", "source_dataset": "P", "sequence_id": "stand-1"},
        ])
        report = module.audit(root)
        assert report["image_count"] == 4
        assert report["coverage"]["fall"]["sequence_count"] == 2
        assert report["coverage"]["fall"]["positive_sequences"] == 1
        assert report["coverage"]["fall"]["negative_sequences"] == 1
        assert report["coverage"]["pose"]["sequence_labels"]["standing"] == 1
        assert report["gates"]["fall_rule_regression"]["ready"] is False
        assert report["gates"]["trainable_temporal_model"]["ready"] is False
        assert report["missing_files"] == []
    print(json.dumps({"ok": True, "script": str(SCRIPT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
