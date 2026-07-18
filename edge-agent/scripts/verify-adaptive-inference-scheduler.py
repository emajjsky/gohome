from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adaptive_inference_scheduler import AdaptiveInferenceScheduler


class ResourceMonitor:
    def __init__(self, thermal_state: str) -> None:
        self.thermal_state = thermal_state

    def snapshot(self, *, now=None) -> dict:
        return {
            "schema_version": "test-resource-v1",
            "available": True,
            "temperature_c": 77.0,
            "thermal_state": self.thermal_state,
        }


def main() -> None:
    scheduler = AdaptiveInferenceScheduler(
        idle_interval_seconds=1.0,
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
        active_hold_seconds=4.0,
        risk_hold_seconds=2.0,
    )
    scheduler.reconcile([24, 25], now=100.0)

    first = scheduler.next_due_camera([24, 25], now=100.0)
    if first != 24:
        raise SystemExit(f"first camera was not selected deterministically: {first}")
    scheduler.mark_started(24, now=100.0)
    scheduler.observe(24, {"person_count": 0, "motion_detected": False}, now=100.1)

    second = scheduler.next_due_camera([24, 25], now=100.1)
    if second != 25:
        raise SystemExit(f"second camera was starved by first camera: {second}")
    scheduler.mark_started(25, now=100.1)
    scheduler.observe(25, {"person_count": 0, "motion_detected": False}, now=100.2)

    if scheduler.next_due_camera([24, 25], now=100.9) is not None:
        raise SystemExit("idle cameras were scheduled faster than the one-second baseline")
    if scheduler.next_due_camera([24, 25], now=101.0) != 24:
        raise SystemExit("idle camera was not due one second after its previous start")

    scheduler.mark_started(24, now=101.0)
    scheduler.observe(
        24,
        {"person_count": 1, "motion_detected": True, "motion_score": 0.08},
        now=101.2,
        frame_age_seconds=0.12,
    )
    active = scheduler.camera_state(24, now=101.2)
    if active["mode"] != "active" or not active["pose_required"]:
        raise SystemExit(f"visible person did not enable active pose sensing: {active}")
    if abs(float(active["interval_seconds"]) - 0.5) > 0.0001:
        raise SystemExit(f"active interval is incorrect: {active}")
    if abs(float(active["next_due_at"]) - 101.5) > 0.0001:
        raise SystemExit(f"active deadline did not use start-to-start pacing: {active}")

    scheduler.mark_started(24, now=101.5)
    scheduler.observe(
        24,
        {
            "person_count": 1,
            "motion_detected": True,
            "fall_candidate": True,
            "pose_factor_graph": {"fast_fall_candidate": True},
        },
        now=101.7,
    )
    risk = scheduler.camera_state(24, now=101.7)
    if risk["mode"] != "risk" or abs(float(risk["interval_seconds"]) - 0.2) > 0.0001:
        raise SystemExit(f"fall candidate did not enter burst mode: {risk}")

    scheduler.reset_camera(25)
    scheduler.reconcile([24, 25], now=102.0)
    scheduler.mark_started(25, now=102.0)
    scheduler.observe(
        25,
        {
            "person_count": 1,
            "fall_candidate": True,
            "pose_fall_candidate": True,
            "pose_fall_score": 0.96,
            "people": [{"normal_lying_zone": True}],
            "poses": [{"posture": "lying", "normal_lying_zone": True}],
            "pose_factor_graph": {"fast_fall_candidate": False, "fast_fall_score": 0.29},
        },
        now=102.1,
    )
    normal_lying = scheduler.camera_state(25, now=102.1)
    if normal_lying["mode"] != "active":
        raise SystemExit(f"normal bed/sofa lying incorrectly entered risk mode: {normal_lying}")

    scheduler.reset_camera(25)
    scheduler.reconcile([24, 25], now=102.2)
    scheduler.mark_started(25, now=102.2)
    scheduler.observe(
        25,
        {
            "person_count": 1,
            "pose_fall_candidate": True,
            "pose_fall_score": 0.96,
            "poses": [{"posture": "lying", "normal_lying_zone": False}],
        },
        now=102.3,
    )
    floor_lying = scheduler.camera_state(25, now=102.3)
    if floor_lying["mode"] != "risk":
        raise SystemExit(f"non-normal lying failed to enter risk mode: {floor_lying}")

    scheduler.reset_camera(25)
    scheduler.reconcile([24, 25], now=102.4)
    scheduler.mark_started(25, now=102.4)
    scheduler.observe(
        25,
        {
            "person_count": 1,
            "fall_candidate": False,
            "pose_fall_candidate": False,
            "fall_score": 0.62,
            "pose_fall_score": 0.24,
            "poses": [{"posture": "sitting", "normal_lying_zone": False}],
            "pose_factor_graph": {"fast_fall_candidate": False, "fast_fall_score": 0.22},
        },
        now=102.5,
    )
    seated_score = scheduler.camera_state(25, now=102.5)
    if seated_score["mode"] != "active":
        raise SystemExit(f"box-only score incorrectly promoted a seated person to risk: {seated_score}")

    scheduler.mark_started(24, now=104.0)
    scheduler.observe(24, {"person_count": 0, "motion_detected": False}, now=104.1)
    held = scheduler.camera_state(24, now=104.1)
    if held["mode"] != "active":
        raise SystemExit(f"risk decay did not retain short active observation: {held}")

    scheduler.mark_started(24, now=106.0)
    scheduler.observe(24, {"person_count": 0, "motion_detected": False}, now=106.1)
    idle = scheduler.camera_state(24, now=106.1)
    if idle["mode"] != "idle" or idle["pose_required"]:
        raise SystemExit(f"expired activity did not return to idle mode: {idle}")

    scheduler.mark_started(24, now=110.0)
    scheduler.observe(24, {"person_count": 0, "motion_detected": False}, now=113.0)
    late = scheduler.camera_state(24, now=113.0)
    if float(late["next_due_at"]) != 113.0 or int(late["deadline_miss_count"]) < 1:
        raise SystemExit(f"late processing did not drop stale deadlines: {late}")

    scheduler.reconcile([25], now=114.0)
    if scheduler.camera_state(24, now=114.0):
        raise SystemExit("removed camera retained scheduler state")

    priority_scheduler = AdaptiveInferenceScheduler(
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
        active_hold_seconds=4.0,
        risk_hold_seconds=2.0,
    )
    priority_scheduler.reconcile([24, 25], now=200.0)
    priority_scheduler.mark_started(24, now=200.0)
    priority_scheduler.observe(
        24,
        {"person_count": 1, "pose_factor_graph": {"fast_fall_candidate": True}},
        now=200.1,
    )
    priority_scheduler.mark_started(25, now=200.1)
    priority_scheduler.observe(25, {"person_count": 1}, now=200.2)
    if priority_scheduler.next_due_camera([24, 25], now=200.6) != 24:
        raise SystemExit("risk camera did not receive global inference priority")

    starvation_scheduler = AdaptiveInferenceScheduler(
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
        active_hold_seconds=4.0,
        risk_hold_seconds=2.0,
        max_starvation_seconds=1.0,
    )
    starvation_scheduler.reconcile([24, 25], now=300.0)
    starvation_scheduler.mark_started(24, now=300.0)
    starvation_scheduler.observe(
        24,
        {"person_count": 1, "pose_factor_graph": {"fast_fall_candidate": True}},
        now=300.1,
    )
    if starvation_scheduler.next_due_camera([24, 25], now=301.1) != 25:
        raise SystemExit("risk priority starved the overdue baseline camera")

    hot_scheduler = AdaptiveInferenceScheduler(
        resource_monitor=ResourceMonitor("hot"),
        active_interval_seconds=0.5,
    )
    hot_scheduler.reconcile([24, 25], now=400.0)
    hot_scheduler.mark_started(24, now=400.0)
    hot_scheduler.observe(24, {"person_count": 1}, now=400.2)
    if hot_scheduler.next_due_camera([24, 25], now=400.3) is not None:
        raise SystemExit("hot resource state did not apply a global cooldown")
    if hot_scheduler.next_due_camera([24, 25], now=400.42) != 25:
        raise SystemExit("global cooldown did not release the next camera fairly")
    hot_status = hot_scheduler.status(now=400.42)
    if hot_status.get("resource", {}).get("thermal_state") != "hot":
        raise SystemExit(f"thermal state missing from scheduler status: {hot_status}")

    print({
        "ok": True,
        "idle_interval_seconds": idle["interval_seconds"],
        "active_interval_seconds": active["interval_seconds"],
        "risk_interval_seconds": risk["interval_seconds"],
        "normal_lying_mode": normal_lying["mode"],
        "floor_lying_mode": floor_lying["mode"],
        "seated_score_mode": seated_score["mode"],
        "independent_camera_rotation": True,
        "stale_deadlines_dropped": True,
        "risk_priority": True,
        "starvation_guard": True,
        "thermal_cooldown": True,
    })


if __name__ == "__main__":
    main()
