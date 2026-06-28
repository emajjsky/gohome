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

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER,
                    type TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'warning',
                    snapshot_id INTEGER,
                    occurred_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id)
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
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    camera_id, type, room, summary, level, snapshot_id, occurred_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
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
                    s.image_path AS snapshot_path
                FROM events e
                LEFT JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN snapshots s ON s.id = e.snapshot_id
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
                    s.image_path AS snapshot_path
                FROM events e
                LEFT JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN snapshots s ON s.id = e.snapshot_id
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
