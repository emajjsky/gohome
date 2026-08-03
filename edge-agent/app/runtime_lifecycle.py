from __future__ import annotations

from threading import Lock, Thread
from time import monotonic
from typing import Any, Callable, Iterable


def stop_components(
    components: Iterable[tuple[str, Callable[[], Any]]],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Stop independent background components within one shared deadline."""
    items = list(components)
    completed: list[str] = []
    errors: dict[str, str] = {}
    result_lock = Lock()

    def stop_one(name: str, stop: Callable[[], Any]) -> None:
        try:
            stop()
        except Exception as exc:
            with result_lock:
                errors[name] = str(exc)
        finally:
            with result_lock:
                completed.append(name)

    started_at = monotonic()
    deadline = started_at + max(0.1, float(timeout_seconds))
    threads = [
        Thread(
            target=stop_one,
            args=(name, stop),
            name=f"gohome-stop-{name}",
            daemon=True,
        )
        for name, stop in items
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - monotonic()))

    completed_set = set(completed)
    return {
        "elapsed_seconds": round(monotonic() - started_at, 3),
        "completed": [name for name, _stop in items if name in completed_set],
        "unfinished": [name for name, _stop in items if name not in completed_set],
        "errors": dict(errors),
    }
