from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    style_source = (ROOT / "app" / "vision" / "skeleton_style.py").read_text(encoding="utf-8")
    diagnostic_path = ROOT / "app" / "vision" / "synchronized_pose_stream.py"
    privacy_path = ROOT / "app" / "vision" / "privacy_stream.py"
    diagnostic_source = diagnostic_path.read_text(encoding="utf-8")
    privacy_source = privacy_path.read_text(encoding="utf-8")
    console_source = (ROOT / "admin" / "console.js").read_text(encoding="utf-8")

    required_constants = {
        "DEFAULT_SKELETON_EDGES",
        "SKELETON_LINE_BGR",
        "SKELETON_JOINT_BGR",
        "SKELETON_OUTLINE_BGR",
        "SKELETON_LINE_WIDTH",
        "SKELETON_OUTLINE_WIDTH",
        "SKELETON_JOINT_RADIUS",
        "SKELETON_JOINT_OUTLINE_RADIUS",
    }
    missing = [name for name in required_constants if name not in style_source]
    if missing:
        raise SystemExit(f"shared skeleton style is missing {missing}")
    for path, source in ((diagnostic_path, diagnostic_source), (privacy_path, privacy_source)):
        if "from .skeleton_style import" not in source:
            raise SystemExit(f"{path.name} does not consume shared skeleton style")
        if "draw_skeleton_pose(" not in source:
            raise SystemExit(f"{path.name} does not use the shared skeleton geometry renderer")
        if "(36, 177, 236)" in source or "(219, 209, 33)" in source:
            raise SystemExit(f"{path.name} contains a private skeleton color")
    if "黄色骨架" in console_source or "原画 + 蓝色骨架" not in console_source:
        raise SystemExit("admin diagnostic skeleton label is not the blue contract")
    if "SKELETON_LINE_WIDTH" not in style_source or "draw_skeleton_pose(" not in style_source:
        raise SystemExit("shared geometry renderer does not own the line width")

    print({"ok": True, "shared_module": "app/vision/skeleton_style.py", "normal_color": "cyan-blue"})


if __name__ == "__main__":
    main()
