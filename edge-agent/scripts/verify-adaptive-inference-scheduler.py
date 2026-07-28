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

    wake_scheduler = AdaptiveInferenceScheduler(
        idle_interval_seconds=1.0,
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
    )
    wake_scheduler.reconcile([24], now=100.0)
    wake_scheduler.signal_activity(24, now=100.0)
    activity_wakeup = wake_scheduler.camera_state(24, now=100.0)
    if (
        activity_wakeup["mode"] != "active"
        or activity_wakeup["pose_required"]
        or float(activity_wakeup["next_due_in_seconds"]) > 0.001
    ):
        raise SystemExit(f"motion gate did not wake the active camera: {activity_wakeup}")
    wake_scheduler.mark_started(24, now=100.0)
    wake_scheduler.observe(24, {"person_count": 1, "motion_detected": True}, now=100.05)
    if not wake_scheduler.camera_state(24, now=100.05)["pose_required"]:
        raise SystemExit("confirmed person did not enable pose inference")
    scheduled_due = float(wake_scheduler.camera_state(24, now=100.05)["next_due_at"])
    wake_scheduler.signal_activity(24, now=100.10)
    retained_due = float(wake_scheduler.camera_state(24, now=100.10)["next_due_at"])
    if abs(scheduled_due - retained_due) > 0.0001:
        raise SystemExit("motion gate bypassed the active inference cadence")
    wake_scheduler.signal_activity(24, now=100.15, risk=True, source="klt_rapid_downward")
    risk_wakeup = wake_scheduler.camera_state(24, now=100.15)
    if (
        risk_wakeup.get("mode") != "risk"
        or risk_wakeup.get("risk_signal_count") != 1
        or risk_wakeup.get("last_risk_signal_source") != "klt_rapid_downward"
        or abs(float(risk_wakeup.get("last_risk_signal_at_monotonic") or 0.0) - 100.15) > 0.0001
    ):
        raise SystemExit(f"risk signal diagnostics are incomplete: {risk_wakeup}")

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
            "inference_backend": "hailo",
            "person_count": 1,
            "motion_detected": True,
        },
        now=101.55,
    )
    accelerated_active = scheduler.camera_state(24, now=101.55)
    if (
        not accelerated_active["accelerated"]
        or abs(float(accelerated_active["interval_seconds"]) - 0.067) > 0.0001
    ):
        raise SystemExit(f"Hailo active cadence was not enabled: {accelerated_active}")

    accelerated_probe_scheduler = AdaptiveInferenceScheduler(
        idle_interval_seconds=1.0,
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
        active_hold_seconds=4.0,
        risk_hold_seconds=2.0,
    )
    accelerated_probe_scheduler.reconcile([30], now=150.0)
    accelerated_probe_scheduler.mark_started(30, now=150.0)
    accelerated_probe_scheduler.observe(
        30,
        {"inference_backend": "hailo", "person_count": 0, "motion_detected": False},
        now=150.04,
    )
    accelerated_probe_scheduler.signal_activity(30, now=150.2, source="motion_gate")
    motion_probe = accelerated_probe_scheduler.camera_state(30, now=150.2)
    if motion_probe["mode"] != "idle" or float(motion_probe["next_due_in_seconds"]) > 0.001:
        raise SystemExit(f"Hailo motion did not remain an immediate idle probe: {motion_probe}")
    accelerated_probe_scheduler.mark_started(30, now=150.2)
    accelerated_probe_scheduler.observe(
        30,
        {"inference_backend": "hailo", "person_count": 0, "motion_detected": True},
        now=150.24,
    )
    motion_only_result = accelerated_probe_scheduler.camera_state(30, now=150.24)
    if motion_only_result["mode"] != "idle" or motion_only_result["pose_required"]:
        raise SystemExit(f"Hailo motion-only result consumed active pose budget: {motion_only_result}")
    accelerated_probe_scheduler.mark_started(30, now=150.7)
    accelerated_probe_scheduler.observe(
        30,
        {"inference_backend": "hailo", "person_count": 1, "motion_detected": True},
        now=150.74,
    )
    confirmed_person_result = accelerated_probe_scheduler.camera_state(30, now=150.74)
    if confirmed_person_result["mode"] != "active" or not confirmed_person_result["pose_required"]:
        raise SystemExit(f"Hailo person result did not sustain active mode: {confirmed_person_result}")

    scheduler.mark_started(24, now=101.6)
    scheduler.observe(
        24,
        {
            "inference_backend": "hailo",
            "person_count": 1,
            "motion_detected": True,
            "fall_candidate": True,
            "pose_factor_graph": {"fast_fall_candidate": True},
        },
        now=101.65,
    )
    accelerated_risk = scheduler.camera_state(24, now=101.65)
    if (
        accelerated_risk["mode"] != "risk"
        or not accelerated_risk["accelerated"]
        or abs(float(accelerated_risk["interval_seconds"]) - 0.05) > 0.0001
    ):
        raise SystemExit(f"Hailo risk cadence was not enabled: {accelerated_risk}")

    scheduler.mark_started(24, now=101.667)
    scheduler.observe(
        24,
        {
            "inference_backend": "cpu",
            "person_count": 1,
            "pose_factor_graph": {"fast_fall_candidate": True},
        },
        now=101.70,
    )
    risk = scheduler.camera_state(24, now=101.70)
    if risk["accelerated"] or abs(float(risk["interval_seconds"]) - 0.2) > 0.0001:
        raise SystemExit(f"CPU fallback did not restore the CPU risk cadence: {risk}")

    scheduler.mark_error(24, now=101.8)
    errored = scheduler.camera_state(24, now=101.8)
    if errored["accelerated"]:
        raise SystemExit(f"scheduler error retained accelerated mode: {errored}")
    if abs(float(errored["next_due_at"]) - 103.8) > 0.0001:
        raise SystemExit(f"scheduler error backoff is incorrect: {errored}")

    scheduler.reset_camera(24)
    scheduler.reconcile([24, 25], now=101.9)
    scheduler.mark_started(24, now=101.9)
    scheduler.observe(
        24,
        {
            "person_count": 1,
            "motion_detected": True,
            "fall_candidate": True,
            "pose_factor_graph": {"fast_fall_candidate": True},
        },
        now=102.0,
    )
    risk = scheduler.camera_state(24, now=102.0)
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
            "pose_factor_graph": {
                "fast_fall_candidate": False,
                "fast_fall_score": 0.68,
                "tracks": [{
                    "normal_lying_zone": True,
                    "factors": {"vertical_drop": False, "motion": False},
                }],
            },
        },
        now=102.1,
    )
    normal_lying = scheduler.camera_state(25, now=102.1)
    if normal_lying["mode"] != "active":
        raise SystemExit(f"normal bed/sofa lying incorrectly entered risk mode: {normal_lying}")

    scheduler.reset_camera(25)
    scheduler.reconcile([24, 25], now=102.15)
    scheduler.mark_started(25, now=102.15)
    scheduler.observe(
        25,
        {
            "person_count": 1,
            "people": [{"normal_lying_zone": True}],
            "poses": [{"posture": "lying", "normal_lying_zone": True}],
            "pose_factor_graph": {
                "fast_fall_candidate": False,
                "fast_fall_score": 0.68,
                "tracks": [{
                    "normal_lying_zone": True,
                    "factors": {"vertical_drop": True, "motion": True},
                }],
            },
        },
        now=102.19,
    )
    sofa_impact = scheduler.camera_state(25, now=102.19)
    if sofa_impact["mode"] != "risk":
        raise SystemExit(f"same-track sofa impact failed to enter risk mode: {sofa_impact}")

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
        "sofa_impact_mode": sofa_impact["mode"],
        "floor_lying_mode": floor_lying["mode"],
        "seated_score_mode": seated_score["mode"],
        "independent_camera_rotation": True,
        "stale_deadlines_dropped": True,
        "risk_priority": True,
        "starvation_guard": True,
        "thermal_cooldown": True,
        "motion_wakeup": True,
        "hailo_motion_probe_only": motion_only_result["mode"] == "idle",
        "hailo_person_sustains_active": confirmed_person_result["mode"] == "active",
        "hailo_active_interval_seconds": accelerated_active["interval_seconds"],
        "hailo_risk_interval_seconds": accelerated_risk["interval_seconds"],
        "cpu_fallback_interval_seconds": risk["interval_seconds"],
        "error_clears_acceleration": not errored["accelerated"],
    })


if __name__ == "__main__":
    main()
