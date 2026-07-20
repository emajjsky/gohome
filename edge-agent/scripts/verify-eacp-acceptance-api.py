from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import main as edge_main


class Service:
    def __init__(self) -> None:
        self.calls = []

    def start(self, *, scenario: str, camera_id: int, label: str = "") -> dict:
        self.calls.append(("start", scenario, camera_id, label))
        return {"status": "active", "scenario": scenario, "camera_id": camera_id, "label": label}

    def status(self) -> dict:
        self.calls.append(("status",))
        return {"status": "active"}

    def finish(self) -> dict:
        self.calls.append(("finish",))
        return {"status": "finished", "result": "passed"}

    def clear(self) -> dict:
        self.calls.append(("clear",))
        return {"status": "idle"}


def main() -> None:
    service = Service()
    edge_main.eacp_acceptance_service = service

    started = edge_main.start_eacp_acceptance({
        "scenario": "simulated_fall",
        "camera_id": 24,
        "label": "客厅模拟",
    })
    if started.get("status") != "active" or service.calls[-1] != ("start", "simulated_fall", 24, "客厅模拟"):
        raise SystemExit(f"acceptance start API is incorrect: {started}, {service.calls}")
    if edge_main.eacp_acceptance_status().get("status") != "active":
        raise SystemExit("acceptance status API is incorrect")
    if edge_main.finish_eacp_acceptance().get("result") != "passed":
        raise SystemExit("acceptance finish API is incorrect")
    if edge_main.clear_eacp_acceptance().get("status") != "idle":
        raise SystemExit("acceptance clear API is incorrect")

    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    if '"/api/eacp-acceptance"' not in source or not edge_main.admin_api_requires_auth("/api/eacp-acceptance"):
        raise SystemExit("acceptance API is not protected by the admin session middleware")

    print({"ok": True, "calls": [item[0] for item in service.calls], "admin_protected": True})


if __name__ == "__main__":
    main()
