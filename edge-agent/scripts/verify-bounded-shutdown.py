#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from threading import Event
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime_lifecycle import stop_components


def main() -> int:
    release = Event()
    calls: list[str] = []

    def quick(name: str) -> None:
        time.sleep(0.05)
        calls.append(name)

    def blocked() -> None:
        release.wait(5.0)

    started_at = time.monotonic()
    result = stop_components(
        [
            ("first", lambda: quick("first")),
            ("second", lambda: quick("second")),
            ("blocked", blocked),
        ],
        timeout_seconds=0.2,
    )
    elapsed = time.monotonic() - started_at
    release.set()

    assert set(calls) == {"first", "second"}
    assert result["completed"] == ["first", "second"]
    assert result["unfinished"] == ["blocked"]
    assert not result["errors"]
    assert elapsed < 0.5
    print({"ok": True, "elapsed_seconds": round(elapsed, 3), "unfinished": result["unfinished"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
