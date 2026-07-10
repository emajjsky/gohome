#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


FOREIGN_PATH_MARKERS = ("/opt/homebrew/", "/Users/", "\\\\Users\\\\")


def read_env(root: Path) -> dict[str, str]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.env_loader import load_env_file

    values: dict[str, str] = {}
    for path in (root / ".env.local", root / ".env"):
        for key, value in load_env_file(path).items():
            values.setdefault(key, value)
    return values


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def import_version(module_name: str) -> str:
    module = importlib.import_module(module_name)
    return str(getattr(module, "__version__", "installed"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Raspberry Pi vision runtime before service start.")
    parser.add_argument("--require-yolo", action="store_true")
    parser.add_argument("--require-pose", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="load both models and run one synthetic frame")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    env = read_env(root)
    checks: list[dict[str, Any]] = []

    cfg_path = Path(sys.prefix) / "pyvenv.cfg"
    cfg_text = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.exists() else ""
    foreign_marker = next((marker for marker in FOREIGN_PATH_MARKERS if marker in cfg_text), "")
    add_check(
        checks,
        "python_environment",
        not foreign_marker,
        f"{sys.executable} ({platform.system()} {platform.machine()})"
        if not foreign_marker
        else f"foreign path marker found in {cfg_path}: {foreign_marker}",
    )

    yolo_model = root / str(env.get("GOHOME_YOLO_MODEL") or "yolo11n.pt")
    if args.require_yolo:
        for module_name in ("torch", "ultralytics"):
            try:
                add_check(checks, module_name, True, import_version(module_name))
            except Exception as exc:
                add_check(checks, module_name, False, str(exc))
        add_check(checks, "yolo_model", yolo_model.is_file(), str(yolo_model))

    if args.require_pose:
        for module_name in ("onnxruntime", "rtmlib"):
            try:
                add_check(checks, module_name, True, import_version(module_name))
            except Exception as exc:
                add_check(checks, module_name, False, str(exc))
        checkpoints = sorted((Path.home() / ".cache/rtmlib/hub/checkpoints").glob("*.onnx"))
        add_check(checks, "rtmpose_checkpoints", len(checkpoints) >= 2, f"{len(checkpoints)} checkpoint(s)")

    if args.smoke and all(item["ok"] for item in checks):
        try:
            import numpy as np
            from ultralytics import YOLO
            from app.vision.pose_rtmpose import RtmposeAnalyzer

            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            YOLO(str(yolo_model)).predict(frame, imgsz=416, classes=[0], device="cpu", verbose=False)
            pose = RtmposeAnalyzer(enabled=True, max_poses=1).analyze(
                frame,
                {"pose_detection_enabled": True},
            )
            add_check(checks, "model_smoke", pose.get("pose_model_status") == "ready", str(pose.get("pose_model_message") or ""))
        except Exception as exc:
            add_check(checks, "model_smoke", False, str(exc))

    ok = all(item["ok"] for item in checks)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
