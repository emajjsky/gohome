from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rule_engine import RuleEngine, build_event_evidence, event_category


def analysis(*, prolonged: bool) -> dict:
    track = {
        "track_id": "c1-p1",
        "bbox": [80, 220, 500, 350],
        "center": [0.45, 0.79],
        "posture": "lying",
        "posture_confidence": 0.91,
        "lying_duration_seconds": 181.0,
        "normal_lying_zone": False,
        "prolonged_floor_lying_candidate": prolonged,
        "fast_fall_candidate": False,
        "fast_fall_score": 0.63,
        "factors": {"low_posture": True, "non_normal_lying_surface": True},
    }
    return {
        "pipeline_version": "test",
        "image_width": 640,
        "image_height": 360,
        "brightness": 100,
        "contrast": 30,
        "black_screen": False,
        "motion_detected": False,
        "motion_score": 0.0,
        "person_count": 1,
        "people": [],
        "pose_count": 1,
        "poses": [],
        "fall_candidate": False,
        "fall_score": 0.0,
        "pose_fall_candidate": False,
        "pose_fall_score": 0.0,
        "meal_candidate": False,
        "stillness_candidate": False,
        "daze_candidate": False,
        "fire_candidate": False,
        "fire_event_candidate": False,
        "fire_score": 0.0,
        "thresholds": {"pose_fall_threshold": 0.78},
        "algorithm_results": {},
        "tags": [],
        "pose_factor_graph": {
            "schema_version": "pose-factor-graph-v1",
            "fast_fall_candidate": False,
            "fast_fall_score": 0.0,
            "fast_fall_track": None,
            "prolonged_floor_lying_candidate": prolonged,
            "prolonged_floor_lying_tracks": [track] if prolonged else [],
        },
        "temporal_evidence_bundle": {
            "schema_version": "temporal-evidence-bundle-v1",
            "track_id": "c1-p1",
            "snapshots": [{"snapshot_id": 9}],
        },
    }


def main() -> None:
    engine = RuleEngine()
    camera = {"id": 1, "name": "客厅", "room": "客厅"}
    snapshot = {"id": 9}
    rules = {
        "fall_detection_enabled": True,
        "person_detection_enabled": True,
        "black_screen_enabled": False,
        "fire_detection_enabled": False,
        "no_person_seconds": 43200,
        "fall_score_threshold": 0.5,
        "fall_confirm_frames": 2,
        "fall_confirm_seconds": 0,
        "fall_recover_frames": 2,
    }
    first = engine.evaluate_snapshot(camera, snapshot, analysis(prolonged=True), rules)
    event = next((item for item in first.candidates if item.event_type == "prolonged_floor_lying"), None)
    if event is None:
        raise SystemExit("first prolonged-floor episode must create an event candidate")
    if event.payload["evidence"]["temporal_evidence_bundle"]["snapshots"][0]["snapshot_id"] != 9:
        raise SystemExit("event evidence must include the temporal snapshot bundle")
    repeated = engine.evaluate_snapshot(camera, snapshot, analysis(prolonged=True), rules)
    if any(item.event_type == "prolonged_floor_lying" for item in repeated.candidates):
        raise SystemExit("same prolonged-floor episode must not create duplicate candidates")
    engine.evaluate_snapshot(camera, snapshot, analysis(prolonged=False), rules)
    resumed = engine.evaluate_snapshot(camera, snapshot, analysis(prolonged=True), rules)
    if not any(item.event_type == "prolonged_floor_lying" for item in resumed.candidates):
        raise SystemExit("a recovered then repeated episode must create a new candidate")
    if event_category("prolonged_floor_lying") != "safety_alert":
        raise SystemExit("prolonged-floor event must be categorized as safety alert")
    evidence = build_event_evidence(
        event_type="prolonged_floor_lying",
        summary="test",
        level="critical",
        analysis=analysis(prolonged=True),
        rule={"id": "prolonged_floor_lying"},
    )
    print(json.dumps({
        "ok": True,
        "event_category": evidence["event_category"],
        "factor_graph_version": evidence["pose_factor_graph"]["schema_version"],
        "dedupe_verified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
