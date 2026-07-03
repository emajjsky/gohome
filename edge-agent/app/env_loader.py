from __future__ import annotations

from pathlib import Path
import os
import re


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_value(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if value[0] == value[-1] and value[0] in {'"', "'"} and len(value) >= 2:
        inner = value[1:-1]
        if value[0] == '"':
            return bytes(inner, "utf-8").decode("unicode_escape")
        return inner
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def load_env_file(file_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not file_path.exists():
        return values
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.match(key):
            continue
        values[key] = _parse_value(raw_value)
    return values


def load_env_files(base_dir: Path, names: tuple[str, ...] = (".env", ".env.local")) -> list[Path]:
    loaded: list[Path] = []
    for name in names:
        file_path = base_dir / name
        if not file_path.exists():
            continue
        values = load_env_file(file_path)
        for key, value in values.items():
            os.environ.setdefault(key, value)
        loaded.append(file_path)
    return loaded
