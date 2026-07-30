#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


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


def configured_runtime_paths(cfg_text: str) -> list[Path]:
    paths: list[Path] = []
    for raw_line in cfg_text.splitlines():
        key, separator, raw_value = raw_line.partition("=")
        if not separator or key.strip() not in {"home", "executable"}:
            continue
        value = raw_value.strip()
        if value:
            paths.append(Path(value))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Raspberry Pi vision runtime before service start.")
    parser.add_argument("--require-yolo", action="store_true")
    parser.add_argument("--require-pose", action="store_true")
    parser.add_argument("--require-hailo", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="load both models and run one synthetic frame")
    parser.add_argument(
        "--hailo-smoke",
        action="store_true",
        help="configure the Hailo pose model and run one synthetic frame",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    env = read_env(root)
    checks: list[dict[str, Any]] = []

    cfg_path = Path(sys.prefix) / "pyvenv.cfg"
    cfg_text = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.exists() else ""
    expected_prefix = (root / ".venv").resolve()
    active_prefix = Path(sys.prefix).resolve()
    runtime_paths = configured_runtime_paths(cfg_text)
    missing_runtime_paths = [str(path) for path in runtime_paths if not path.exists()]
    environment_ok = bool(
        cfg_path.is_file()
        and active_prefix == expected_prefix
        and runtime_paths
        and not missing_runtime_paths
    )
    add_check(
        checks,
        "python_environment",
        environment_ok,
        (
            f"{sys.executable} ({platform.system()} {platform.machine()})"
            if environment_ok
            else json.dumps({
                "active_prefix": str(active_prefix),
                "expected_prefix": str(expected_prefix),
                "config": str(cfg_path),
                "configured_runtime_paths": [str(path) for path in runtime_paths],
                "missing_runtime_paths": missing_runtime_paths,
            }, ensure_ascii=False)
        ),
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

    hailo_model = Path(
        env.get("GOHOME_HAILO_POSE_MODEL")
        or "/usr/share/hailo-models/yolov8s_pose_h8.hef"
    )
    hailo_object_model = Path(
        env.get("GOHOME_HAILO_OBJECT_MODEL")
        or "/usr/share/hailo-models/yolov8s_h8.hef"
    )
    if args.require_hailo or args.hailo_smoke:
        try:
            hailo_platform = importlib.import_module("hailo_platform")
            add_check(checks, "hailo_platform", True, str(hailo_platform.__file__))
        except Exception as exc:
            add_check(checks, "hailo_platform", False, str(exc))
        add_check(checks, "hailo_pose_model", hailo_model.is_file(), str(hailo_model))
        add_check(checks, "hailo_object_model", hailo_object_model.is_file(), str(hailo_object_model))
        device_path = Path("/dev/hailo0")
        add_check(checks, "hailo_device", device_path.exists(), str(device_path))

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

    hailo_prerequisites = {
        item["name"]: item["ok"]
        for item in checks
        if item["name"] in {"hailo_platform", "hailo_pose_model", "hailo_object_model", "hailo_device"}
    }
    if args.hailo_smoke and all(hailo_prerequisites.values()):
        backend = None
        object_backend = None
        try:
            import numpy as np
            from app.vision.hailo_object import HailoObjectBackend
            from app.vision.hailo_pose import HailoPoseBackend

            backend = HailoPoseBackend(mode="hailo", model_path=str(hailo_model))
            object_backend = HailoObjectBackend(mode="hailo", model_path=str(hailo_object_model))
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            result = backend.analyze(
                frame,
                {"pose_max_poses": 1},
            )
            object_result = object_backend.analyze(frame, {"camera_id": "smoke"})
            status = backend.status()
            object_status = object_backend.status()
            add_check(
                checks,
                "hailo_model_smoke",
                result is not None
                and object_result is not None
                and status.get("status") == "ready"
                and object_status.get("status") == "ready"
                and status.get("shared_vdevice", {}).get("lease_count") == 2,
                json.dumps({"pose": status, "object": object_status}, ensure_ascii=False),
            )
        except Exception as exc:
            add_check(checks, "hailo_model_smoke", False, str(exc))
        finally:
            if backend is not None:
                backend.close()
            if object_backend is not None:
                object_backend.close()

    ok = all(item["ok"] for item in checks)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
