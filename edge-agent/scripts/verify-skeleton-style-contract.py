from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


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
        if "(36, 177, 236)" in source or "(219, 209, 33)" in source:
            raise SystemExit(f"{path.name} contains a private skeleton color")
    if "黄色骨架" in console_source or "原画 + 蓝色骨架" not in console_source:
        raise SystemExit("admin diagnostic skeleton label is not the blue contract")
    if "SKELETON_LINE_WIDTH" not in diagnostic_source or "SKELETON_LINE_WIDTH" not in privacy_source:
        raise SystemExit("diagnostic and privacy renderers do not share line width")

    diagnostic_imports = imported_names(diagnostic_path)
    privacy_imports = imported_names(privacy_path)
    shared_render_constants = required_constants - {"SKELETON_BOX_BGR", "SKELETON_BOX_WIDTH"}
    for name in shared_render_constants:
        if name not in diagnostic_imports:
            raise SystemExit(f"diagnostic renderer does not import {name}")
        if name not in privacy_imports:
            raise SystemExit(f"privacy renderer does not import {name}")

    print({"ok": True, "shared_module": "app/vision/skeleton_style.py", "normal_color": "cyan-blue"})


if __name__ == "__main__":
    main()
