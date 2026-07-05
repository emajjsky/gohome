from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.event_agent import EventAgent
from app.storage import Storage


def candidate(event_type: str, snapshot_id: int, score: float) -> dict:
    return {
        "event_type": event_type,
        "summary": "客厅摄像头 检测到疑似明火视觉线索。" if event_type == "fire_candidate" else "客厅摄像头 画面疑似黑屏或遮挡。",
        "level": "critical" if event_type == "fire_candidate" else "warning",
        "snapshot_id": snapshot_id,
        "payload": {
            "rule": {"id": event_type, "reason": "验证候选去重。"},
            "evidence": {
                "schema_version": "gohome-event-evidence-v1",
                "event_category": "safety_alert" if event_type == "fire_candidate" else "device_alert",
                "metrics": {"fire_score": score},
            },
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(Path(tmpdir) / "agent.db")
        storage.init_schema()
        camera = storage.create_camera(
            {
                "name": "客厅摄像头",
                "room": "客厅",
                "stream_url": "rtsp://192.168.1.11:554/1/2",
                "username": "admin",
                "enabled": True,
            }
        )
        base_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        promoted_ids: list[int] = []
        for index, score in enumerate([0.08, 0.09, 0.10]):
            row = storage.create_event_candidate(
                camera_id=int(camera["id"]),
                detection_result_id=None,
                rule_evaluation_id=None,
                candidate=candidate("fire_candidate", index + 1, score),
                evaluated_at=(base_time + timedelta(minutes=index * 5)).isoformat(),
            )
            storage.update_event_candidate_status(int(row["id"]), "promoted", promoted_event_id=100 + index)
            promoted_ids.append(int(row["id"]))
        black = storage.create_event_candidate(
            camera_id=int(camera["id"]),
            detection_result_id=None,
            rule_evaluation_id=None,
            candidate=candidate("black_screen", 9, 0.0),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        storage.update_event_candidate_status(int(black["id"]), "promoted", promoted_event_id=200)

        active = storage.list_event_candidates(limit=10, status="active")
        fire_rows = [row for row in active if row["event_type"] == "fire_candidate"]
        if len(fire_rows) != 1:
            raise SystemExit(f"expected one active fire candidate, got {len(fire_rows)}: {active}")
        if int(fire_rows[0]["id"]) != promoted_ids[-1]:
            raise SystemExit(f"expected latest fire candidate {promoted_ids[-1]}, got {fire_rows[0]['id']}")

        event_agent = EventAgent(storage, notifier=None, throttle_seconds=300)
        if event_agent._throttle_seconds("fire_candidate") < 1800:
            raise SystemExit("fire throttle should be at least 30 minutes")

        print(
            json.dumps(
                {
                    "ok": True,
                    "active_count": len(active),
                    "latest_fire_candidate_id": fire_rows[0]["id"],
                    "fire_throttle_seconds": event_agent._throttle_seconds("fire_candidate"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
