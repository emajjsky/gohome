from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rule_engine import RuleEngine
from app.schemas import RulesUpdate
from app.storage import Storage


OBSOLETE_RULE_COLUMNS = {
    "fire_detection_enabled",
    "fire_event_score_threshold",
    "fire_motion_threshold",
    "fire_temporal_threshold",
    "fire_confirm_frames",
}


def create_legacy_rules_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE rules (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                capture_interval_seconds INTEGER NOT NULL,
                motion_threshold REAL NOT NULL DEFAULT 0.015,
                black_brightness_threshold REAL NOT NULL DEFAULT 18,
                black_contrast_threshold REAL NOT NULL DEFAULT 4,
                yolo_confidence REAL NOT NULL DEFAULT 0.20,
                no_motion_seconds INTEGER NOT NULL,
                black_screen_enabled INTEGER NOT NULL,
                no_motion_enabled INTEGER NOT NULL,
                person_detection_enabled INTEGER NOT NULL,
                fall_detection_enabled INTEGER NOT NULL,
                fall_score_threshold REAL NOT NULL DEFAULT 0.50,
                fall_confirm_frames INTEGER NOT NULL DEFAULT 2,
                fall_confirm_seconds INTEGER NOT NULL DEFAULT 4,
                fall_recover_frames INTEGER NOT NULL DEFAULT 2,
                activity_detection_enabled INTEGER NOT NULL DEFAULT 1,
                fire_detection_enabled INTEGER NOT NULL DEFAULT 1,
                fire_event_score_threshold REAL NOT NULL DEFAULT 0.12,
                fire_motion_threshold REAL NOT NULL DEFAULT 0.035,
                fire_temporal_threshold REAL NOT NULL DEFAULT 0.018,
                fire_confirm_frames INTEGER NOT NULL DEFAULT 5,
                no_person_seconds INTEGER NOT NULL,
                offline_enabled INTEGER NOT NULL,
                notification_enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO rules VALUES (
                1, 17, 0.02, 19, 5, 0.24, 600, 1, 1, 1, 1,
                0.55, 3, 5, 3, 1, 1, 0.14, 0.04, 0.02, 6,
                720, 1, 1, 'legacy-updated-at'
            )
            """
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "edge.db"
        create_legacy_rules_table(db_path)
        storage = Storage(db_path)
        storage.init_schema()

        with storage.connect() as conn:
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(rules)").fetchall()}
        leaked_columns = sorted(columns & OBSOLETE_RULE_COLUMNS)
        if leaked_columns:
            raise SystemExit(f"obsolete rule columns survived migration: {leaked_columns}")

        rules = storage.get_rules()
        if OBSOLETE_RULE_COLUMNS & rules.keys():
            raise SystemExit("obsolete fire settings leaked through the rule API")
        if rules["capture_interval_seconds"] != 17 or rules["updated_at"] != "legacy-updated-at":
            raise SystemExit(f"rule migration changed retained values: {rules}")

        updated = storage.update_rules({"capture_interval_seconds": 19, "fire_detection_enabled": True})
        if updated["capture_interval_seconds"] != 19 or OBSOLETE_RULE_COLUMNS & updated.keys():
            raise SystemExit(f"legacy patch was not filtered: {updated}")

        schema_fields = RulesUpdate.model_fields if hasattr(RulesUpdate, "model_fields") else RulesUpdate.__fields__
        if OBSOLETE_RULE_COLUMNS & schema_fields.keys():
            raise SystemExit("obsolete fire settings remain in RulesUpdate")

        camera = storage.create_camera({
            "name": "客厅摄像头",
            "room": "客厅",
            "stream_url": "rtsp://127.0.0.1/1/2",
            "enabled": True,
        })
        engine = RuleEngine()
        legacy_analysis = {
            "black_screen": False,
            "motion_detected": True,
            "motion_score": 1.0,
            "person_count": 0,
            "fall_candidate": False,
            "pose_fall_candidate": False,
            "pose_factor_graph": {},
            "fire_candidate": True,
            "fire_event_candidate": True,
            "fire_score": 1.0,
            "fire_temporal_score": 1.0,
            "thresholds": {"fire_score_threshold": 0.0},
        }
        for _ in range(10):
            evaluation = engine.evaluate_snapshot(camera, {"id": None}, legacy_analysis, updated)
            if any(candidate.event_type == "fire_candidate" for candidate in evaluation.candidates):
                raise SystemExit("legacy analysis fields created a new fire event candidate")
            if any(key.startswith("fire_") for key in evaluation.state):
                raise SystemExit(f"legacy fire state leaked into rule evaluation: {evaluation.state}")

        historical = storage.create_event(
            event_type="fire_candidate",
            summary="历史版本事件",
            level="critical",
            camera_id=int(camera["id"]),
            room="客厅",
            payload={"source": "legacy"},
        )
        loaded = storage.get_event(int(historical["id"]))
        if loaded is None or loaded["type"] != "fire_candidate" or loaded["payload"].get("source") != "legacy":
            raise SystemExit(f"historical event is no longer auditable: {loaded}")

        print({
            "ok": True,
            "removed_rule_columns": len(OBSOLETE_RULE_COLUMNS),
            "legacy_frames_ignored": 10,
            "historical_event_id": int(historical["id"]),
        })


if __name__ == "__main__":
    main()
