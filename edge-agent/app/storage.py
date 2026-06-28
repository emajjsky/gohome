from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import json
import sqlite3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    stream_url TEXT NOT NULL,
                    username TEXT,
                    password TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_seen_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    image_path TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    brightness REAL,
                    motion_score REAL,
                    person_count INTEGER,
                    tags TEXT NOT NULL DEFAULT '[]',
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(camera_id) REFERENCES cameras(id)
                );

                CREATE TABLE IF NOT EXISTS detection_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    snapshot_id INTEGER,
                    captured_at TEXT NOT NULL,
                    frame_width INTEGER,
                    frame_height INTEGER,
                    detector_backend TEXT NOT NULL DEFAULT 'basic',
                    model_name TEXT,
                    model_version TEXT,
                    person_count INTEGER,
                    objects_json TEXT NOT NULL DEFAULT '[]',
                    quality_flags_json TEXT NOT NULL DEFAULT '[]',
                    raw_confidence_summary_json TEXT NOT NULL DEFAULT '{}',
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id)
                );

                CREATE TABLE IF NOT EXISTS rule_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    snapshot_id INTEGER,
                    detection_result_id INTEGER,
                    rule_set_version TEXT,
                    evaluated_at TEXT NOT NULL,
                    matched_rules_json TEXT NOT NULL DEFAULT '[]',
                    window_seconds INTEGER,
                    explanation TEXT NOT NULL DEFAULT '',
                    score REAL,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    candidates_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(detection_result_id) REFERENCES detection_results(id)
                );

                CREATE TABLE IF NOT EXISTS event_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    detection_result_id INTEGER,
                    rule_evaluation_id INTEGER,
                    event_type TEXT NOT NULL,
                    candidate_level TEXT NOT NULL DEFAULT 'warning',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    dedupe_key TEXT NOT NULL,
                    source_evaluations_json TEXT NOT NULL DEFAULT '[]',
                    evidence_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'new',
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    promoted_event_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(detection_result_id) REFERENCES detection_results(id),
                    FOREIGN KEY(rule_evaluation_id) REFERENCES rule_evaluations(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER,
                    detection_result_id INTEGER,
                    rule_evaluation_id INTEGER,
                    candidate_id INTEGER,
                    type TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'warning',
                    snapshot_id INTEGER,
                    occurred_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(detection_result_id) REFERENCES detection_results(id),
                    FOREIGN KEY(rule_evaluation_id) REFERENCES rule_evaluations(id),
                    FOREIGN KEY(candidate_id) REFERENCES event_candidates(id)
                );

                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    capture_interval_seconds INTEGER NOT NULL,
                    motion_threshold REAL NOT NULL DEFAULT 0.015,
                    black_brightness_threshold REAL NOT NULL DEFAULT 18,
                    black_contrast_threshold REAL NOT NULL DEFAULT 4,
                    yolo_confidence REAL NOT NULL DEFAULT 0.35,
                    no_motion_seconds INTEGER NOT NULL,
                    black_screen_enabled INTEGER NOT NULL,
                    no_motion_enabled INTEGER NOT NULL,
                    person_detection_enabled INTEGER NOT NULL,
                    fall_detection_enabled INTEGER NOT NULL,
                    no_person_seconds INTEGER NOT NULL,
                    offline_enabled INTEGER NOT NULL,
                    notification_enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "snapshots", "person_count", "INTEGER")
            self._ensure_column(conn, "snapshots", "width", "INTEGER")
            self._ensure_column(conn, "snapshots", "height", "INTEGER")
            self._ensure_column(conn, "snapshots", "analysis_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "events", "detection_result_id", "INTEGER")
            self._ensure_column(conn, "events", "rule_evaluation_id", "INTEGER")
            self._ensure_column(conn, "events", "candidate_id", "INTEGER")
            self._ensure_column(conn, "rules", "person_detection_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "rules", "fall_detection_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "rules", "no_person_seconds", "INTEGER NOT NULL DEFAULT 300")
            self._ensure_column(conn, "rules", "motion_threshold", "REAL NOT NULL DEFAULT 0.015")
            self._ensure_column(conn, "rules", "black_brightness_threshold", "REAL NOT NULL DEFAULT 18")
            self._ensure_column(conn, "rules", "black_contrast_threshold", "REAL NOT NULL DEFAULT 4")
            self._ensure_column(conn, "rules", "yolo_confidence", "REAL NOT NULL DEFAULT 0.35")
            exists = conn.execute("SELECT id FROM rules WHERE id = 1").fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO rules (
                        id,
                        capture_interval_seconds,
                        motion_threshold,
                        black_brightness_threshold,
                        black_contrast_threshold,
                        yolo_confidence,
                        no_motion_seconds,
                        black_screen_enabled,
                        no_motion_enabled,
                        person_detection_enabled,
                        fall_detection_enabled,
                        no_person_seconds,
                        offline_enabled,
                        notification_enabled,
                        updated_at
                    )
                    VALUES (1, 5, 0.015, 18, 4, 0.35, 300, 1, 1, 0, 0, 300, 1, 0, ?)
                    """,
                    (now_iso(),),
                )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _camera_to_dict(self, row: sqlite3.Row, include_secret: bool = False) -> Dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        if not include_secret:
            data.pop("password", None)
        return data

    def list_cameras(self, include_secret: bool = False) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM cameras ORDER BY id DESC").fetchall()
        return [self._camera_to_dict(row, include_secret=include_secret) for row in rows]

    def get_camera(self, camera_id: int, include_secret: bool = False) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        return self._camera_to_dict(row, include_secret=include_secret) if row else None

    def create_camera(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cameras (
                    name, room, stream_url, username, password, enabled,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'unknown', ?, ?)
                """,
                (
                    payload["name"],
                    payload.get("room") or "",
                    payload["stream_url"],
                    payload.get("username"),
                    payload.get("password"),
                    1 if payload.get("enabled", True) else 0,
                    timestamp,
                    timestamp,
                ),
            )
            camera_id = int(cursor.lastrowid)
        camera = self.get_camera(camera_id)
        if camera is None:
            raise RuntimeError("Camera was not persisted")
        return camera

    def update_camera(self, camera_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"name", "room", "stream_url", "username", "password", "enabled"}
        current = self.get_camera(camera_id, include_secret=True)
        if current is None:
            return None

        next_values = {**current}
        for key, value in patch.items():
            if key in allowed and value is not None:
                next_values[key] = value

        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE cameras
                SET name = ?,
                    room = ?,
                    stream_url = ?,
                    username = ?,
                    password = ?,
                    enabled = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_values["name"],
                    next_values.get("room") or "",
                    next_values["stream_url"],
                    next_values.get("username"),
                    next_values.get("password"),
                    1 if next_values.get("enabled", True) else 0,
                    timestamp,
                    camera_id,
                ),
            )
        return self.get_camera(camera_id)

    def delete_camera(self, camera_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        return cursor.rowcount > 0

    def update_camera_status(self, camera_id: int, status: str, last_error: str = "") -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            if status == "online":
                conn.execute(
                    """
                    UPDATE cameras
                    SET status = ?, last_seen_at = ?, last_error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, timestamp, timestamp, camera_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE cameras
                    SET status = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, last_error, timestamp, camera_id),
                )

    def _snapshot_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["tags"] = json.loads(data["tags"] or "[]")
        data["analysis"] = json.loads(data.pop("analysis_json", "{}") or "{}")
        data["image_url"] = f"/snapshots/{data['image_path']}"
        return data

    def _detection_result_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["objects"] = json.loads(data.pop("objects_json", "[]") or "[]")
        data["quality_flags"] = json.loads(data.pop("quality_flags_json", "[]") or "[]")
        data["raw_confidence_summary"] = json.loads(data.pop("raw_confidence_summary_json", "{}") or "{}")
        data["analysis"] = json.loads(data.pop("analysis_json", "{}") or "{}")
        return data

    def create_detection_result(
        self,
        camera_id: int,
        snapshot_id: Optional[int],
        captured_at: str,
        width: Optional[int],
        height: Optional[int],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        objects = [
            {
                "category": "person",
                "confidence": person.get("confidence"),
                "bbox": person.get("bbox"),
                "fall_candidate": bool(person.get("fall_candidate")),
            }
            for person in people
        ]
        quality_flags = list(analysis.get("tags") or [])
        raw_confidence_summary = {
            "person_confidences": [person.get("confidence") for person in people if person.get("confidence") is not None],
            "motion_score": analysis.get("motion_score"),
            "brightness": analysis.get("brightness"),
            "contrast": analysis.get("contrast"),
        }
        detector_backend = str(analysis.get("detector_backend") or "basic")
        model_name = analysis.get("model_name")
        if detector_backend == "yolo" and not model_name:
            model_name = analysis.get("yolo_model")
        created_at = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detection_results (
                    camera_id, snapshot_id, captured_at, frame_width, frame_height,
                    detector_backend, model_name, model_version, person_count,
                    objects_json, quality_flags_json, raw_confidence_summary_json,
                    analysis_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    snapshot_id,
                    captured_at,
                    width,
                    height,
                    detector_backend,
                    model_name,
                    analysis.get("model_version"),
                    analysis.get("person_count"),
                    json.dumps(objects, ensure_ascii=False),
                    json.dumps(quality_flags, ensure_ascii=False),
                    json.dumps(raw_confidence_summary, ensure_ascii=False),
                    json.dumps(analysis or {}, ensure_ascii=False),
                    created_at,
                ),
            )
            detection_result_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM detection_results WHERE id = ?", (detection_result_id,)).fetchone()
        if row is None:
            raise RuntimeError("DetectionResult was not persisted")
        return self._detection_result_to_dict(row)

    def latest_detection_result(self, camera_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM detection_results WHERE camera_id = ? ORDER BY captured_at DESC, id DESC LIMIT 1",
                (camera_id,),
            ).fetchone()
        return self._detection_result_to_dict(row) if row else None

    def _rule_evaluation_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["matched_rules"] = json.loads(data.pop("matched_rules_json", "[]") or "[]")
        data["state"] = json.loads(data.pop("state_json", "{}") or "{}")
        data["candidates"] = json.loads(data.pop("candidates_json", "[]") or "[]")
        return data

    def create_rule_evaluation(
        self,
        camera_id: int,
        snapshot_id: Optional[int],
        detection_result_id: Optional[int],
        evaluation: Dict[str, Any],
        rule_set_version: Optional[str],
    ) -> Dict[str, Any]:
        candidates = list(evaluation.get("candidates") or [])
        matched_rules = []
        explanations: list[str] = []
        for candidate in candidates:
            rule = ((candidate.get("payload") or {}).get("rule")) or {}
            if rule:
                matched_rules.append(rule)
                reason = rule.get("reason") or candidate.get("summary")
                if reason:
                    explanations.append(str(reason))
        no_motion = (evaluation.get("state") or {}).get("no_motion_seconds")
        no_person = (evaluation.get("state") or {}).get("no_person_seconds")
        windows = [value for value in [no_motion, no_person] if isinstance(value, (int, float))]
        created_at = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO rule_evaluations (
                    camera_id, snapshot_id, detection_result_id, rule_set_version, evaluated_at,
                    matched_rules_json, window_seconds, explanation, score,
                    state_json, candidates_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    snapshot_id,
                    detection_result_id,
                    rule_set_version,
                    evaluation.get("evaluated_at") or created_at,
                    json.dumps(matched_rules, ensure_ascii=False),
                    int(max(windows)) if windows else None,
                    "；".join(explanations),
                    float(len(candidates)) if candidates else 0.0,
                    json.dumps(evaluation.get("state") or {}, ensure_ascii=False),
                    json.dumps(candidates, ensure_ascii=False),
                    created_at,
                ),
            )
            evaluation_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM rule_evaluations WHERE id = ?", (evaluation_id,)).fetchone()
        if row is None:
            raise RuntimeError("RuleEvaluation was not persisted")
        return self._rule_evaluation_to_dict(row)

    def latest_rule_evaluation(self, camera_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rule_evaluations WHERE camera_id = ? ORDER BY evaluated_at DESC, id DESC LIMIT 1",
                (camera_id,),
            ).fetchone()
        return self._rule_evaluation_to_dict(row) if row else None

    def _event_candidate_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["source_evaluations"] = json.loads(data.pop("source_evaluations_json", "[]") or "[]")
        data["evidence_snapshot_ids"] = json.loads(data.pop("evidence_snapshot_ids_json", "[]") or "[]")
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        return data

    def create_event_candidate(
        self,
        camera_id: int,
        detection_result_id: Optional[int],
        rule_evaluation_id: Optional[int],
        candidate: Dict[str, Any],
        evaluated_at: Optional[str],
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        snapshot_id = candidate.get("snapshot_id")
        dedupe_key = f"{camera_id}:{candidate.get('event_type')}:{snapshot_id or 'none'}"
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO event_candidates (
                    camera_id, detection_result_id, rule_evaluation_id, event_type, candidate_level,
                    started_at, ended_at, dedupe_key, source_evaluations_json, evidence_snapshot_ids_json,
                    status, summary, payload_json, promoted_event_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    detection_result_id,
                    rule_evaluation_id,
                    candidate.get("event_type"),
                    candidate.get("level") or "warning",
                    evaluated_at or timestamp,
                    evaluated_at or timestamp,
                    dedupe_key,
                    json.dumps([rule_evaluation_id] if rule_evaluation_id else [], ensure_ascii=False),
                    json.dumps([snapshot_id] if snapshot_id else [], ensure_ascii=False),
                    "new",
                    candidate.get("summary") or "",
                    json.dumps(candidate.get("payload") or {}, ensure_ascii=False),
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            candidate_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM event_candidates WHERE id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise RuntimeError("EventCandidate was not persisted")
        return self._event_candidate_to_dict(row)

    def update_event_candidate_status(
        self,
        candidate_id: int,
        status: str,
        promoted_event_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE event_candidates
                SET status = ?, promoted_event_id = COALESCE(?, promoted_event_id), updated_at = ?
                WHERE id = ?
                """,
                (status, promoted_event_id, now_iso(), candidate_id),
            )
            row = conn.execute("SELECT * FROM event_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return self._event_candidate_to_dict(row) if row else None

    def create_snapshot(
        self,
        camera_id: int,
        image_path: str,
        width: Optional[int],
        height: Optional[int],
        brightness: float,
        motion_score: Optional[float],
        tags: Iterable[str],
        person_count: Optional[int] = None,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO snapshots (
                    camera_id, image_path, captured_at, width, height,
                    brightness, motion_score, person_count, tags, analysis_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    image_path,
                    now_iso(),
                    width,
                    height,
                    brightness,
                    motion_score,
                    person_count,
                    json.dumps(list(tags)),
                    json.dumps(analysis or {}, ensure_ascii=False),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise RuntimeError("Snapshot was not persisted")
        return self._snapshot_to_dict(row)

    def latest_snapshot(self, camera_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if camera_id is None:
                row = conn.execute("SELECT * FROM snapshots ORDER BY captured_at DESC LIMIT 1").fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM snapshots WHERE camera_id = ? ORDER BY captured_at DESC LIMIT 1",
                    (camera_id,),
                ).fetchone()
        return self._snapshot_to_dict(row) if row else None

    def create_event(
        self,
        event_type: str,
        summary: str,
        level: str = "warning",
        camera_id: Optional[int] = None,
        room: str = "",
        snapshot_id: Optional[int] = None,
        detection_result_id: Optional[int] = None,
        rule_evaluation_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    camera_id, detection_result_id, rule_evaluation_id, candidate_id,
                    type, room, summary, level, snapshot_id, occurred_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    detection_result_id,
                    rule_evaluation_id,
                    candidate_id,
                    event_type,
                    room,
                    summary,
                    level,
                    snapshot_id,
                    now_iso(),
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            event_id = int(cursor.lastrowid)
        event = self.get_event(event_id)
        if event is None:
            raise RuntimeError("Event was not persisted")
        return event

    def _event_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["acknowledged"] = bool(data["acknowledged"])
        data["payload"] = json.loads(data["payload"] or "{}")
        if data.get("snapshot_path"):
            data["snapshot_url"] = f"/snapshots/{data['snapshot_path']}"
        return data

    def list_events(self, limit: int = 50, acknowledged: Optional[bool] = None) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if acknowledged is not None:
            where = "WHERE e.acknowledged = ?"
            params.append(1 if acknowledged else 0)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    e.*,
                    c.name AS camera_name,
                    s.image_path AS snapshot_path,
                    ec.status AS candidate_status
                FROM events e
                LEFT JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN snapshots s ON s.id = e.snapshot_id
                LEFT JOIN event_candidates ec ON ec.id = e.candidate_id
                {where}
                ORDER BY e.occurred_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._event_to_dict(row) for row in rows]

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    e.*,
                    c.name AS camera_name,
                    s.image_path AS snapshot_path,
                    ec.status AS candidate_status
                FROM events e
                LEFT JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN snapshots s ON s.id = e.snapshot_id
                LEFT JOIN event_candidates ec ON ec.id = e.candidate_id
                WHERE e.id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._event_to_dict(row) if row else None

    def update_event(self, event_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_event(event_id)
        if current is None:
            return None

        acknowledged = current["acknowledged"]
        if patch.get("acknowledged") is not None:
            acknowledged = bool(patch["acknowledged"])

        payload = current.get("payload") or {}
        if patch.get("resolution"):
            payload["resolution"] = patch["resolution"]
            payload["resolved_at"] = now_iso()

        with self.connect() as conn:
            conn.execute(
                """
                UPDATE events
                SET acknowledged = ?, payload = ?
                WHERE id = ?
                """,
                (1 if acknowledged else 0, json.dumps(payload, ensure_ascii=False), event_id),
            )
        return self.get_event(event_id)

    def clear_events(self, scope: str = "acknowledged") -> Dict[str, Any]:
        if scope not in {"acknowledged", "all"}:
            raise ValueError("Unsupported event clear scope")

        with self.connect() as conn:
            if scope == "acknowledged":
                cursor = conn.execute("DELETE FROM events WHERE acknowledged = 1")
            else:
                cursor = conn.execute("DELETE FROM events")
            deleted = cursor.rowcount
        return {"deleted": deleted, "scope": scope}

    def event_exists_recent(self, camera_id: Optional[int], event_type: str, seconds: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM events
                WHERE camera_id IS ? AND type = ? AND occurred_at >= ?
                LIMIT 1
                """,
                (camera_id, event_type, cutoff),
            ).fetchone()
        return row is not None

    def get_rules(self) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rules WHERE id = 1").fetchone()
        if row is None:
            raise RuntimeError("Rules row is missing")
        data = dict(row)
        for key in [
            "black_screen_enabled",
            "no_motion_enabled",
            "person_detection_enabled",
            "fall_detection_enabled",
            "offline_enabled",
            "notification_enabled",
        ]:
            data[key] = bool(data[key])
        return data

    def update_rules(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "capture_interval_seconds",
            "motion_threshold",
            "black_brightness_threshold",
            "black_contrast_threshold",
            "yolo_confidence",
            "no_motion_seconds",
            "black_screen_enabled",
            "no_motion_enabled",
            "person_detection_enabled",
            "fall_detection_enabled",
            "no_person_seconds",
            "offline_enabled",
            "notification_enabled",
        }
        current = self.get_rules()
        next_values = {**current}
        for key, value in patch.items():
            if key in allowed and value is not None:
                next_values[key] = value

        with self.connect() as conn:
            conn.execute(
                """
                UPDATE rules
                SET
                    capture_interval_seconds = ?,
                    motion_threshold = ?,
                    black_brightness_threshold = ?,
                    black_contrast_threshold = ?,
                    yolo_confidence = ?,
                    no_motion_seconds = ?,
                    black_screen_enabled = ?,
                    no_motion_enabled = ?,
                    person_detection_enabled = ?,
                    fall_detection_enabled = ?,
                    no_person_seconds = ?,
                    offline_enabled = ?,
                    notification_enabled = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    int(next_values["capture_interval_seconds"]),
                    float(next_values["motion_threshold"]),
                    float(next_values["black_brightness_threshold"]),
                    float(next_values["black_contrast_threshold"]),
                    float(next_values["yolo_confidence"]),
                    int(next_values["no_motion_seconds"]),
                    1 if next_values["black_screen_enabled"] else 0,
                    1 if next_values["no_motion_enabled"] else 0,
                    1 if next_values["person_detection_enabled"] else 0,
                    1 if next_values["fall_detection_enabled"] else 0,
                    int(next_values["no_person_seconds"]),
                    1 if next_values["offline_enabled"] else 0,
                    1 if next_values["notification_enabled"] else 0,
                    now_iso(),
                ),
            )
        return self.get_rules()

    def daily_summary(self) -> Dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as conn:
            events_count = conn.execute(
                "SELECT COUNT(*) AS count FROM events WHERE occurred_at LIKE ?",
                (f"{today}%",),
            ).fetchone()["count"]
            latest_event = conn.execute(
                """
                SELECT summary FROM events
                WHERE occurred_at LIKE ?
                ORDER BY occurred_at DESC
                LIMIT 1
                """,
                (f"{today}%",),
            ).fetchone()
            cameras_count = conn.execute("SELECT COUNT(*) AS count FROM cameras").fetchone()["count"]
            online_count = conn.execute(
                "SELECT COUNT(*) AS count FROM cameras WHERE status = 'online'"
            ).fetchone()["count"]

        if latest_event:
            main_message = latest_event["summary"]
        elif cameras_count == 0:
            main_message = "还没有添加摄像头，先接入一个局域网 RTSP 摄像头。"
        else:
            main_message = "当前没有新的异常事件，守护服务正在运行。"

        return {
            "date": today,
            "main_message": main_message,
            "events_count": events_count,
            "cameras_count": cameras_count,
            "online_cameras_count": online_count,
            "suggested_action": "查看守护状态",
        }
