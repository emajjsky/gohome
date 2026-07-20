from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eacp_acceptance import EacpAcceptanceService


class Clock:
    def __init__(self) -> None:
        self.monotonic = 100.0
        self.utc = datetime(2026, 7, 20, 3, 0, 0, tzinfo=timezone.utc)

    def tick(self, seconds: float) -> None:
        self.monotonic += seconds
        self.utc += timedelta(seconds=seconds)


def runtime(
    *,
    anchors: int,
    risk_signals: int,
    risk_hints: int,
    last_risk: float | None,
    risk_history: list[float] | None = None,
) -> dict:
    return {
        "inference_scheduler": {
            "cameras": [{
                "camera_id": 24,
                "mode": "risk" if risk_signals else "active",
                "observed_count": anchors,
                "deadline_miss_count": 2,
                "risk_signal_count": risk_signals,
                "last_risk_signal_at_monotonic": last_risk,
                "risk_signals": [
                    {"at_monotonic": value, "source": "test"}
                    for value in (risk_history or [])
                ],
                "effective_fps": 3.4,
            }],
            "resource": {"temperature_c": 68.5, "thermal_state": "normal"},
        },
        "continual_pose": {
            "cameras": [{
                "camera_id": 24,
                "observed_count": anchors,
                "tracked_count": anchors * 3,
                "risk_hint_count": risk_hints,
                "last_risk_hint_at_monotonic": last_risk,
            }],
        },
        "camera_streams": {"managed_stream_count": 2},
        "last_error": "",
        "continual_pose_error": "",
    }


def main() -> None:
    clock = Clock()
    state = {"runtime": runtime(anchors=10, risk_signals=0, risk_hints=0, last_risk=None)}
    events: list[dict] = []
    candidates: list[dict] = []
    uploads: list[dict] = []
    cloud = {"ok": True, "records": []}
    cloud_calls = 0

    def resolve_cloud() -> dict:
        nonlocal cloud_calls
        cloud_calls += 1
        return dict(cloud)

    with tempfile.TemporaryDirectory(prefix="gohome-eacp-acceptance-") as temp_dir:
        service = EacpAcceptanceService(
            state_path=Path(temp_dir) / "acceptance.json",
            runtime_resolver=lambda: state["runtime"],
            events_resolver=lambda: list(events),
            candidates_resolver=lambda: list(candidates),
            uploads_resolver=lambda: list(uploads),
            cloud_verification_resolver=resolve_cloud,
            utcnow=lambda: clock.utc,
            monotonic_clock=lambda: clock.monotonic,
        )
        started = service.start(scenario="simulated_fall", camera_id=24, label="客厅低风险模拟")
        if started["status"] != "active" or started["scenario"] != "simulated_fall":
            raise SystemExit(f"acceptance session did not start: {started}")
        if cloud_calls != 0:
            raise SystemExit(f"cloud verification was polled before a safety event: {cloud_calls}")

        clock.tick(2.0)
        state["runtime"] = runtime(
            anchors=17,
            risk_signals=1,
            risk_hints=1,
            last_risk=100.3,
            risk_history=[100.3],
        )
        events.append({
            "id": 81,
            "camera_id": 24,
            "type": "fall_candidate",
            "level": "critical",
            "created_at": "2026-07-20T03:00:01.800000+00:00",
            "payload": {
                "evaluation": {
                    "state": {
                        "fall_confirmation_path": "dynamic_low_position",
                        "fall_confirm_seconds": 2.1,
                        "fall_dynamic_low_count": 4,
                        "fall_transition": {"age_seconds": 3.2},
                    },
                },
                "evidence": {
                    "temporal_evidence_bundle": {
                        "snapshots": [{"snapshot_id": 1}, {"snapshot_id": 2}, {"snapshot_id": 3}],
                    },
                },
            },
        })
        candidates.append({"id": 91, "camera_id": 24, "event_type": "fall_candidate", "promoted_event_id": 81})
        uploads.extend([
            {"id": 1, "event_id": 81, "job_type": "media_upload", "status": "completed"},
            {"id": 2, "event_id": 81, "job_type": "media_upload", "status": "completed"},
            {"id": 3, "event_id": 81, "job_type": "media_upload", "status": "completed"},
            {"id": 4, "event_id": 81, "job_type": "event_upload", "status": "completed"},
        ])
        cloud["records"] = [{
            "edge_event_id": "81",
            "verification": {
                "status": "confirmed",
                "confidence": 0.91,
                "result": {"reason": "三帧显示连续倒地过程。"},
            },
        }]

        report = service.status()
        metrics = report["metrics"]
        if metrics["model_anchor_count"] != 7 or abs(metrics["model_anchor_fps"] - 3.5) > 0.001:
            raise SystemExit(f"anchor metrics are incorrect: {metrics}")
        if metrics["risk_signal_count"] != 1 or metrics["risk_hint_count"] != 1:
            raise SystemExit(f"risk metrics are incomplete: {metrics}")
        if abs(float(metrics["first_risk_latency_seconds"]) - 0.3) > 0.001:
            raise SystemExit(f"risk latency is incorrect: {metrics}")
        if report["events"][0]["evidence_frame_count"] != 3:
            raise SystemExit(f"three-frame evidence was not counted: {report}")
        if report["events"][0]["cloud_verification"]["status"] != "confirmed":
            raise SystemExit(f"cloud verification was not joined: {report}")
        if report["events"][0]["cloud_verification"].get("reason") != "三帧显示连续倒地过程。":
            raise SystemExit(f"cloud verification reason is missing: {report}")
        event_metrics = report["events"][0]
        if event_metrics.get("confirmation_path") != "dynamic_low_position":
            raise SystemExit(f"event confirmation path is missing: {event_metrics}")
        if event_metrics.get("action_to_event_seconds") != 3.2 or event_metrics.get("low_confirmation_seconds") != 2.1:
            raise SystemExit(f"event action latency metrics are incorrect: {event_metrics}")
        if report["checks"]["simulated_fall_event"] != "passed":
            raise SystemExit(f"fall acceptance did not pass: {report['checks']}")
        rejected_checks = service._checks(
            scenario="simulated_fall",
            events=[{
                "event_type": "fall_candidate",
                "evidence_frame_count": 3,
                "event_upload_status": "completed",
                "cloud_verification": {"status": "rejected"},
            }],
            finalizing=True,
        )
        if rejected_checks.get("cloud_confirmed") != "failed":
            raise SystemExit(f"a cloud-rejected simulated fall must not pass acceptance: {rejected_checks}")

        clock.tick(70.0)
        state["runtime"] = runtime(
            anchors=100,
            risk_signals=71,
            risk_hints=1,
            last_risk=170.0,
            risk_history=[float(value) for value in range(107, 171)],
        )
        truncated_metrics = service.status()["metrics"]
        if truncated_metrics.get("first_risk_latency_seconds") is not None:
            raise SystemExit(f"truncated risk history must not report a false first latency: {truncated_metrics}")
        if truncated_metrics.get("first_risk_latency_status") != "history_truncated":
            raise SystemExit(f"truncated risk history status is missing: {truncated_metrics}")

        finished = service.finish()
        if finished["status"] != "finished" or finished["result"] != "passed":
            raise SystemExit(f"finished fall session result is incorrect: {finished}")

        clock.tick(1.0)
        state["runtime"] = runtime(anchors=20, risk_signals=1, risk_hints=1, last_risk=100.3)
        service.start(scenario="walking", camera_id=24, label="正常走动")
        baseline_event_id = max(event["id"] for event in events)
        events.append({
            "id": baseline_event_id + 1,
            "camera_id": 24,
            "type": "fall_candidate",
            "level": "critical",
            "created_at": clock.utc.isoformat(),
            "payload": {},
        })
        false_alarm = service.finish()
        if false_alarm["result"] != "failed" or false_alarm["checks"]["unexpected_safety_event"] != "failed":
            raise SystemExit(f"negative scenario did not fail on a safety event: {false_alarm}")

    print({
        "ok": True,
        "fall_result": finished["result"],
        "negative_result": false_alarm["result"],
        "risk_latency_seconds": report["metrics"]["first_risk_latency_seconds"],
        "evidence_frame_count": report["events"][0]["evidence_frame_count"],
    })


if __name__ == "__main__":
    main()
