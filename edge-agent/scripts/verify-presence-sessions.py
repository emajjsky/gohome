from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(Path(tmpdir) / "agent.db")
        storage.init_schema()
        camera = storage.create_camera({
            "name": "客厅摄像头",
            "room": "客厅",
            "stream_url": "rtsp://192.168.1.11/live",
            "enabled": True,
        })
        camera_id = int(camera["id"])
        storage.upsert_presence_session(
            camera_id=camera_id,
            observed_at="2026-07-11T10:00:00+00:00",
            person_count=1,
            payload={"track_ids": ["c1-p1"]},
        )
        session = storage.upsert_presence_session(
            camera_id=camera_id,
            observed_at="2026-07-11T10:00:05+00:00",
            person_count=2,
            payload={"track_ids": ["c1-p1", "c1-p2"]},
        )
        if int(session["sample_count"]) != 2 or int(session["max_person_count"]) != 2:
            raise SystemExit(f"presence samples were not merged: {session}")

        storage.update_camera(camera_id, {"enabled": False})
        closed = storage.list_presence_sessions(status="closed")
        if len(closed) != 1 or closed[0]["close_reason"] != "camera_disabled":
            raise SystemExit(f"disabling camera must close presence session: {closed}")

        storage.update_camera(camera_id, {"enabled": True})
        storage.upsert_presence_session(
            camera_id=camera_id,
            observed_at="2026-07-11T11:00:00+00:00",
            person_count=1,
        )
        if not storage.delete_camera(camera_id):
            raise SystemExit("camera delete failed")
        closed = storage.list_presence_sessions(status="closed")
        if not any(item["close_reason"] == "camera_deleted" for item in closed):
            raise SystemExit(f"deleting camera must close runtime state: {closed}")

        print(json.dumps({"ok": True, "closed_sessions": len(closed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
