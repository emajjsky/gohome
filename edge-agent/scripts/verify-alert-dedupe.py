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


class SilentNotifier:
    def send(self, **_kwargs) -> None:
        return None


def candidate(event_type: str, snapshot_id: int, score: float) -> dict:
    if event_type == "fall_candidate":
        summary = "客厅摄像头 检测到快速倒地过程。"
    else:
        summary = "客厅摄像头 画面疑似黑屏或遮挡。"
    return {
        "event_type": event_type,
        "summary": summary,
        "level": "critical" if event_type == "fall_candidate" else "warning",
        "snapshot_id": snapshot_id,
        "payload": {
            "rule": {"id": event_type, "reason": "验证候选去重。"},
            "evidence": {
                "schema_version": "gohome-event-evidence-v1",
                "event_category": "safety_alert" if event_type == "fall_candidate" else "device_alert",
                "metrics": {"score": score},
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
                candidate=candidate("black_screen", index + 1, score),
                evaluated_at=(base_time + timedelta(minutes=index * 5)).isoformat(),
            )
            storage.update_event_candidate_status(int(row["id"]), "promoted", promoted_event_id=100 + index)
            promoted_ids.append(int(row["id"]))
        active = storage.list_event_candidates(limit=10, status="active")
        black_rows = [row for row in active if row["event_type"] == "black_screen"]
        if len(black_rows) != 1:
            raise SystemExit(f"expected one active black-screen candidate, got {len(black_rows)}: {active}")
        if int(black_rows[0]["id"]) != promoted_ids[-1]:
            raise SystemExit(f"expected latest black-screen candidate {promoted_ids[-1]}, got {black_rows[0]['id']}")

        event_agent = EventAgent(storage, notifier=SilentNotifier(), throttle_seconds=300)

        first_fall_candidate = storage.create_event_candidate(
            camera_id=int(camera["id"]),
            detection_result_id=None,
            rule_evaluation_id=None,
            candidate=candidate("fall_candidate", 21, 0.91),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        first_fall = event_agent.emit(
            event_type="fall_candidate",
            summary="客厅摄像头 检测到快速倒地过程。",
            level="critical",
            camera=camera,
            candidate_id=int(first_fall_candidate["id"]),
            payload={"rule": {"id": "fall_candidate"}},
        )
        if not first_fall:
            raise SystemExit("first fall candidate must create an event")

        repeated_fall_candidate = storage.create_event_candidate(
            camera_id=int(camera["id"]),
            detection_result_id=None,
            rule_evaluation_id=None,
            candidate=candidate("fall_candidate", 22, 0.93),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        repeated_fall = event_agent.emit(
            event_type="fall_candidate",
            summary="客厅摄像头 连续命中快速倒地过程。",
            level="critical",
            camera=camera,
            candidate_id=int(repeated_fall_candidate["id"]),
            payload={"rule": {"id": "fall_candidate"}},
        )
        if repeated_fall is not None:
            raise SystemExit("same-action fall evidence must aggregate into the recent event")
        aggregated_rows = storage.list_event_candidates(limit=10, status="aggregated")
        aggregated = next(
            (row for row in aggregated_rows if int(row["id"]) == int(repeated_fall_candidate["id"])),
            None,
        )
        if not aggregated or int(aggregated.get("promoted_event_id") or 0) != int(first_fall["id"]):
            raise SystemExit(f"repeated fall candidate was not linked to its incident: {aggregated_rows}")
        aggregated_event = storage.get_event(int(first_fall["id"])) or {}
        aggregation = (aggregated_event.get("payload") or {}).get("candidate_aggregation") or {}
        if aggregation.get("repeat_count") != 1 or aggregation.get("total_candidate_count") != 2:
            raise SystemExit(f"event aggregation audit data is incomplete: {aggregation}")
        finalizer = next(
            (
                job for job in storage.list_upload_jobs(limit=20, job_type="event_evidence_finalize")
                if int(job.get("event_id") or 0) == int(first_fall["id"])
            ),
            None,
        )
        if finalizer is None:
            raise SystemExit("fall incident did not defer cloud publication until evidence finalization")
        finalized_event = storage.finalize_event_evidence(int(first_fall["id"]))
        storage.enqueue_event_upload_jobs(finalized_event)
        event_upload = next(
            (
                job for job in storage.list_upload_jobs(limit=20, job_type="event_upload")
                if int(job.get("event_id") or 0) == int(first_fall["id"])
            ),
            None,
        )
        uploaded_aggregation = ((event_upload or {}).get("payload") or {}).get("payload", {}).get("candidate_aggregation") or {}
        if uploaded_aggregation.get("repeat_count") != 1:
            raise SystemExit(f"finalized cloud event did not receive aggregate evidence: {event_upload}")

        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=9)).isoformat()
        with storage.connect() as conn:
            conn.execute("UPDATE events SET occurred_at = ? WHERE id = ?", (expired_at, int(first_fall["id"])))
        later_fall_candidate = storage.create_event_candidate(
            camera_id=int(camera["id"]),
            detection_result_id=None,
            rule_evaluation_id=None,
            candidate=candidate("fall_candidate", 23, 0.95),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        later_fall = event_agent.emit(
            event_type="fall_candidate",
            summary="客厅摄像头 检测到新的快速倒地过程。",
            level="critical",
            camera=camera,
            candidate_id=int(later_fall_candidate["id"]),
            payload={"rule": {"id": "fall_candidate"}},
        )
        if not later_fall or int(later_fall["id"]) == int(first_fall["id"]):
            raise SystemExit("a distinct later fall must create a new cloud-review event")

        print(
            json.dumps(
                {
                    "ok": True,
                    "active_count": len(active),
                    "latest_black_screen_candidate_id": black_rows[0]["id"],
                    "fall_aggregation_window_seconds": event_agent._throttle_seconds("fall_candidate"),
                    "aggregated_candidate_id": repeated_fall_candidate["id"],
                    "later_event_id": later_fall["id"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
