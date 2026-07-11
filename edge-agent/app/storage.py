from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional
import json
import sqlite3
import shutil


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    password_hash = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1).hex()
    return salt.hex(), password_hash


def verify_password(password: str, salt_hex: str, password_hash: str) -> bool:
    _, computed_hash = hash_password(password, salt_hex=salt_hex)
    return secrets.compare_digest(computed_hash, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
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

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS families (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS family_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(family_id, user_id),
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS device_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL DEFAULT 'edge-agent',
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    bound_by_user_id INTEGER NOT NULL,
                    bound_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(family_id, device_id),
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(bound_by_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS device_binding_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    code TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active',
                    issued_by_user_id INTEGER NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    consumed_by_device_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(issued_by_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS device_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL UNIQUE,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL DEFAULT 'edge-agent',
                    token_hash TEXT NOT NULL UNIQUE,
                    token_prefix TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    issued_by_code_id INTEGER,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_seen_at TEXT,
                    last_heartbeat_at TEXT,
                    last_heartbeat_ip TEXT,
                    last_heartbeat_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(issued_by_code_id) REFERENCES device_binding_codes(id)
                );

                CREATE TABLE IF NOT EXISTS app_push_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    app_install_id TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'ios',
                    provider TEXT NOT NULL DEFAULT 'apns',
                    push_token TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    token_prefix TEXT NOT NULL,
                    device_name TEXT NOT NULL DEFAULT '',
                    app_version TEXT NOT NULL DEFAULT '',
                    environment TEXT NOT NULL DEFAULT 'production',
                    status TEXT NOT NULL DEFAULT 'active',
                    last_registered_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, app_install_id),
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS video_service_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    node_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'origin',
                    region TEXT NOT NULL DEFAULT 'local',
                    service_url TEXT NOT NULL DEFAULT '',
                    media_url TEXT NOT NULL DEFAULT '',
                    public_base_url TEXT NOT NULL DEFAULT '',
                    health_status TEXT NOT NULL DEFAULT 'active',
                    priority INTEGER NOT NULL DEFAULT 100,
                    capabilities_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    last_seen_at TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(family_id, node_id),
                    FOREIGN KEY(family_id) REFERENCES families(id)
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

                CREATE TABLE IF NOT EXISTS event_ingests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    event_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(device_id, idempotency_key),
                    FOREIGN KEY(event_id) REFERENCES events(id)
                );

                CREATE TABLE IF NOT EXISTS upload_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    object_type TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 100,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    family_id INTEGER,
                    device_id TEXT NOT NULL DEFAULT '',
                    event_id INTEGER,
                    snapshot_id INTEGER,
                    camera_id INTEGER,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(event_id) REFERENCES events(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(camera_id) REFERENCES cameras(id)
                );

                CREATE TABLE IF NOT EXISTS observation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    observation_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    started_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 1,
                    last_snapshot_id INTEGER,
                    last_detection_result_id INTEGER,
                    last_rule_evaluation_id INTEGER,
                    last_event_candidate_id INTEGER,
                    summary TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(last_snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(last_detection_result_id) REFERENCES detection_results(id),
                    FOREIGN KEY(last_rule_evaluation_id) REFERENCES rule_evaluations(id),
                    FOREIGN KEY(last_event_candidate_id) REFERENCES event_candidates(id)
                );

                CREATE TABLE IF NOT EXISTS presence_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    started_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 1,
                    max_person_count INTEGER NOT NULL DEFAULT 1,
                    representative_snapshot_id INTEGER,
                    close_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(representative_snapshot_id) REFERENCES snapshots(id)
                );

                CREATE TABLE IF NOT EXISTS posture_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    track_id TEXT NOT NULL,
                    posture TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    started_at TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 1,
                    mean_confidence REAL NOT NULL DEFAULT 0,
                    max_confidence REAL NOT NULL DEFAULT 0,
                    normal_lying_zone INTEGER NOT NULL DEFAULT 0,
                    scene_zone_id TEXT,
                    scene_zone_label TEXT,
                    representative_snapshot_id INTEGER,
                    close_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id),
                    FOREIGN KEY(representative_snapshot_id) REFERENCES snapshots(id)
                );

                CREATE TABLE IF NOT EXISTS device_sync_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL UNIQUE,
                    family_id INTEGER NOT NULL,
                    desired_app_version TEXT NOT NULL DEFAULT '',
                    desired_model_version TEXT NOT NULL DEFAULT '',
                    desired_rules_json TEXT NOT NULL DEFAULT '{}',
                    desired_rule_version TEXT NOT NULL DEFAULT '',
                    desired_config_json TEXT NOT NULL DEFAULT '{}',
                    desired_config_version TEXT NOT NULL DEFAULT '',
                    reported_app_version TEXT NOT NULL DEFAULT '',
                    reported_model_version TEXT NOT NULL DEFAULT '',
                    applied_rule_version TEXT NOT NULL DEFAULT '',
                    reported_status_json TEXT NOT NULL DEFAULT '{}',
                    last_seen_at TEXT,
                    last_sync_at TEXT,
                    last_applied_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id)
                );

                CREATE TABLE IF NOT EXISTS device_rollouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    rollout_mode TEXT NOT NULL DEFAULT 'canary',
                    status TEXT NOT NULL DEFAULT 'draft',
                    target_app_version TEXT NOT NULL DEFAULT '',
                    target_model_version TEXT NOT NULL DEFAULT '',
                    rules_patch_json TEXT NOT NULL DEFAULT '{}',
                    config_patch_json TEXT NOT NULL DEFAULT '{}',
                    scope_device_ids_json TEXT NOT NULL DEFAULT '[]',
                    canary_device_ids_json TEXT NOT NULL DEFAULT '[]',
                    applied_device_ids_json TEXT NOT NULL DEFAULT '[]',
                    rolled_back_device_ids_json TEXT NOT NULL DEFAULT '[]',
                    previous_targets_json TEXT NOT NULL DEFAULT '{}',
                    created_by_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    promoted_at TEXT,
                    rolled_back_at TEXT,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(created_by_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS media_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    event_id INTEGER,
                    snapshot_id INTEGER UNIQUE,
                    source_snapshot_path TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL DEFAULT 'localfs',
                    bucket TEXT NOT NULL DEFAULT 'local',
                    object_key TEXT NOT NULL UNIQUE,
                    content_type TEXT NOT NULL DEFAULT 'image/jpeg',
                    byte_size INTEGER NOT NULL DEFAULT 0,
                    checksum_sha256 TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'uploaded',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    uploaded_at TEXT,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(event_id) REFERENCES events(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id)
                );

                CREATE TABLE IF NOT EXISTS media_upload_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    created_by_user_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    byte_size INTEGER NOT NULL DEFAULT 0,
                    provider TEXT NOT NULL DEFAULT 'signed-localfs',
                    bucket TEXT NOT NULL DEFAULT 'public-media',
                    object_key TEXT NOT NULL UNIQUE,
                    upload_token_hash TEXT NOT NULL UNIQUE,
                    asset_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    expires_at TEXT NOT NULL,
                    uploaded_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                    FOREIGN KEY(asset_id) REFERENCES media_assets(id)
                );

                CREATE TABLE IF NOT EXISTS package_releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    package_type TEXT NOT NULL,
                    version TEXT NOT NULL,
                    asset_id INTEGER NOT NULL,
                    install_strategy TEXT NOT NULL DEFAULT 'file',
                    entry_path TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_by_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(family_id, package_type, version),
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(asset_id) REFERENCES media_assets(id),
                    FOREIGN KEY(created_by_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS package_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    package_type TEXT NOT NULL,
                    target_version TEXT NOT NULL,
                    release_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    staged_path TEXT NOT NULL DEFAULT '',
                    installed_path TEXT NOT NULL DEFAULT '',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT,
                    finished_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(release_id) REFERENCES package_releases(id)
                );

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    event_id INTEGER,
                    channel TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    recipient TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    delivered_at TEXT,
                    FOREIGN KEY(family_id) REFERENCES families(id),
                    FOREIGN KEY(event_id) REFERENCES events(id)
                );

                CREATE TABLE IF NOT EXISTS elder_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    elder_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    birthday TEXT NOT NULL DEFAULT '',
                    lunar_birthday TEXT NOT NULL DEFAULT '',
                    living_status TEXT NOT NULL DEFAULT '',
                    primary_room TEXT NOT NULL DEFAULT '',
                    likes_json TEXT NOT NULL DEFAULT '[]',
                    dislikes_json TEXT NOT NULL DEFAULT '[]',
                    diet_notes_json TEXT NOT NULL DEFAULT '[]',
                    health_conditions_json TEXT NOT NULL DEFAULT '[]',
                    medication_notes TEXT NOT NULL DEFAULT '',
                    routine_json TEXT NOT NULL DEFAULT '{}',
                    emergency_contacts_json TEXT NOT NULL DEFAULT '[]',
                    home_area TEXT NOT NULL DEFAULT '',
                    privacy_level TEXT NOT NULL DEFAULT 'family_only',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(family_id, elder_id),
                    FOREIGN KEY(family_id) REFERENCES families(id)
                );

                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    elder_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    remind_before_days_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT 'manual',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id)
                );

                CREATE TABLE IF NOT EXISTS message_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    family_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    elder_id TEXT NOT NULL DEFAULT '',
                    message_type TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'warm',
                    title TEXT NOT NULL,
                    subtitle TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    facts_json TEXT NOT NULL DEFAULT '[]',
                    image_mode TEXT NOT NULL DEFAULT 'none',
                    image_url TEXT NOT NULL DEFAULT '',
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    source_json TEXT NOT NULL DEFAULT '[]',
                    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
                    source_media_ids_json TEXT NOT NULL DEFAULT '[]',
                    generated_by TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES families(id)
                );

                CREATE TABLE IF NOT EXISTS rules (
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
            self._ensure_column(conn, "rules", "person_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fall_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fall_score_threshold", "REAL NOT NULL DEFAULT 0.50")
            self._ensure_column(conn, "rules", "fall_confirm_frames", "INTEGER NOT NULL DEFAULT 2")
            self._ensure_column(conn, "rules", "fall_confirm_seconds", "INTEGER NOT NULL DEFAULT 4")
            self._ensure_column(conn, "rules", "fall_recover_frames", "INTEGER NOT NULL DEFAULT 2")
            self._ensure_column(conn, "rules", "activity_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fire_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fire_event_score_threshold", "REAL NOT NULL DEFAULT 0.12")
            self._ensure_column(conn, "rules", "fire_motion_threshold", "REAL NOT NULL DEFAULT 0.035")
            self._ensure_column(conn, "rules", "fire_temporal_threshold", "REAL NOT NULL DEFAULT 0.018")
            self._ensure_column(conn, "rules", "fire_confirm_frames", "INTEGER NOT NULL DEFAULT 5")
            self._ensure_column(conn, "rules", "no_person_seconds", "INTEGER NOT NULL DEFAULT 300")
            self._ensure_column(conn, "rules", "motion_threshold", "REAL NOT NULL DEFAULT 0.015")
            self._ensure_column(conn, "rules", "black_brightness_threshold", "REAL NOT NULL DEFAULT 18")
            self._ensure_column(conn, "rules", "black_contrast_threshold", "REAL NOT NULL DEFAULT 4")
            self._ensure_column(conn, "rules", "yolo_confidence", "REAL NOT NULL DEFAULT 0.20")
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
                        fall_score_threshold,
                        fall_confirm_frames,
                        fall_confirm_seconds,
                        fall_recover_frames,
                        activity_detection_enabled,
                        fire_detection_enabled,
                        fire_event_score_threshold,
                        fire_motion_threshold,
                        fire_temporal_threshold,
                        fire_confirm_frames,
                        no_person_seconds,
                        offline_enabled,
                        notification_enabled,
                        updated_at
                    )
                    VALUES (1, 5, 0.015, 18, 4, 0.20, 300, 1, 1, 1, 1, 0.50, 2, 4, 2, 1, 1, 0.12, 0.035, 0.018, 5, 300, 1, 1, ?)
                    """,
                    (now_iso(),),
                )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at ON snapshots(captured_at, id);
                CREATE INDEX IF NOT EXISTS idx_detection_results_created_at ON detection_results(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_rule_evaluations_created_at ON rule_evaluations(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_event_candidates_created_at ON event_candidates(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_upload_jobs_completed_at ON upload_jobs(status, completed_at, id);
                CREATE INDEX IF NOT EXISTS idx_events_snapshot_id ON events(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_events_detection_result_id ON events(detection_result_id);
                CREATE INDEX IF NOT EXISTS idx_events_rule_evaluation_id ON events(rule_evaluation_id);
                CREATE INDEX IF NOT EXISTS idx_events_candidate_id ON events(candidate_id);
                CREATE INDEX IF NOT EXISTS idx_event_candidates_detection_result_id
                    ON event_candidates(detection_result_id);
                CREATE INDEX IF NOT EXISTS idx_event_candidates_rule_evaluation_id
                    ON event_candidates(rule_evaluation_id);
                CREATE INDEX IF NOT EXISTS idx_rule_evaluations_detection_result_id
                    ON rule_evaluations(detection_result_id);
                CREATE INDEX IF NOT EXISTS idx_rule_evaluations_snapshot_id ON rule_evaluations(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_detection_results_snapshot_id ON detection_results(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_presence_sessions_camera_status
                    ON presence_sessions(camera_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_posture_episodes_camera_status
                    ON posture_episodes(camera_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_posture_episodes_track_status
                    ON posture_episodes(camera_id, track_id, status, updated_at);
                """
            )

    def prune_runtime_history(
        self,
        *,
        snapshot_dir: Path,
        retention_hours: int = 24,
        completed_upload_retention_days: int = 7,
        batch_size: int = 5000,
    ) -> Dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(retention_hours)))).isoformat()
        upload_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(completed_upload_retention_days)))
        ).isoformat()
        limit = max(100, min(int(batch_size), 20000))
        removed_paths: list[str] = []
        deleted: Dict[str, int] = {}

        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")

            deleted["upload_jobs"] = conn.execute(
                """
                DELETE FROM upload_jobs
                WHERE id IN (
                    SELECT id FROM upload_jobs
                    WHERE status = 'completed'
                      AND COALESCE(completed_at, updated_at, created_at) < ?
                    ORDER BY id
                    LIMIT ?
                )
                """,
                (upload_cutoff, limit),
            ).rowcount

            deleted["event_candidates"] = conn.execute(
                """
                DELETE FROM event_candidates
                WHERE id IN (
                    SELECT ec.id
                    FROM event_candidates ec
                    WHERE ec.created_at < ?
                      AND ec.id NOT IN (SELECT candidate_id FROM events WHERE candidate_id IS NOT NULL)
                      AND ec.id NOT IN (
                          SELECT last_event_candidate_id FROM observation_logs
                          WHERE last_event_candidate_id IS NOT NULL
                      )
                      AND ec.id NOT IN (
                          SELECT MAX(latest.id) FROM event_candidates latest
                          GROUP BY latest.camera_id, latest.event_type
                      )
                    ORDER BY ec.id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

            deleted["rule_evaluations"] = conn.execute(
                """
                DELETE FROM rule_evaluations
                WHERE id IN (
                    SELECT re.id
                    FROM rule_evaluations re
                    WHERE re.created_at < ?
                      AND re.id NOT IN (
                          SELECT rule_evaluation_id FROM events WHERE rule_evaluation_id IS NOT NULL
                      )
                      AND re.id NOT IN (
                          SELECT rule_evaluation_id FROM event_candidates WHERE rule_evaluation_id IS NOT NULL
                      )
                      AND re.id NOT IN (
                          SELECT last_rule_evaluation_id FROM observation_logs
                          WHERE last_rule_evaluation_id IS NOT NULL
                      )
                      AND re.id NOT IN (
                          SELECT MAX(latest.id) FROM rule_evaluations latest GROUP BY latest.camera_id
                      )
                    ORDER BY re.id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

            deleted["detection_results"] = conn.execute(
                """
                DELETE FROM detection_results
                WHERE id IN (
                    SELECT dr.id
                    FROM detection_results dr
                    WHERE dr.created_at < ?
                      AND dr.id NOT IN (
                          SELECT detection_result_id FROM events WHERE detection_result_id IS NOT NULL
                      )
                      AND dr.id NOT IN (
                          SELECT detection_result_id FROM event_candidates WHERE detection_result_id IS NOT NULL
                      )
                      AND dr.id NOT IN (
                          SELECT detection_result_id FROM rule_evaluations WHERE detection_result_id IS NOT NULL
                      )
                      AND dr.id NOT IN (
                          SELECT last_detection_result_id FROM observation_logs
                          WHERE last_detection_result_id IS NOT NULL
                      )
                      AND dr.id NOT IN (
                          SELECT MAX(latest.id) FROM detection_results latest GROUP BY latest.camera_id
                      )
                    ORDER BY dr.id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

            snapshot_rows = conn.execute(
                """
                SELECT s.id, s.image_path
                FROM snapshots s
                WHERE s.captured_at < ?
                  AND s.id NOT IN (SELECT snapshot_id FROM events WHERE snapshot_id IS NOT NULL)
                  AND s.id NOT IN (
                      SELECT snapshot_id FROM detection_results WHERE snapshot_id IS NOT NULL
                  )
                  AND s.id NOT IN (
                      SELECT snapshot_id FROM rule_evaluations WHERE snapshot_id IS NOT NULL
                  )
                  AND s.id NOT IN (
                      SELECT last_snapshot_id FROM observation_logs WHERE last_snapshot_id IS NOT NULL
                  )
                  AND s.id NOT IN (
                      SELECT representative_snapshot_id FROM presence_sessions
                      WHERE representative_snapshot_id IS NOT NULL AND status = 'open'
                  )
                  AND s.id NOT IN (
                      SELECT representative_snapshot_id FROM posture_episodes
                      WHERE representative_snapshot_id IS NOT NULL AND status = 'open'
                  )
                  AND s.id NOT IN (
                      SELECT snapshot_id FROM upload_jobs
                      WHERE snapshot_id IS NOT NULL AND status != 'completed'
                  )
                  AND s.id NOT IN (
                      SELECT snapshot_id FROM media_assets WHERE snapshot_id IS NOT NULL
                  )
                  AND s.id NOT IN (
                      SELECT MAX(latest.id) FROM snapshots latest GROUP BY latest.camera_id
                  )
                ORDER BY s.id
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
            snapshot_ids = [int(row["id"]) for row in snapshot_rows]
            removed_paths = [str(row["image_path"] or "") for row in snapshot_rows]
            if snapshot_ids:
                placeholders = ",".join("?" for _ in snapshot_ids)
                deleted["snapshots"] = conn.execute(
                    f"DELETE FROM snapshots WHERE id IN ({placeholders})",
                    snapshot_ids,
                ).rowcount
            else:
                deleted["snapshots"] = 0

        snapshot_root = snapshot_dir.resolve()
        deleted_files = 0
        skipped_files = 0
        for relative_path in removed_paths:
            if not relative_path:
                continue
            candidate = (snapshot_root / relative_path).resolve()
            if snapshot_root not in candidate.parents:
                skipped_files += 1
                continue
            try:
                candidate.unlink(missing_ok=True)
                deleted_files += 1
            except OSError:
                skipped_files += 1

        return {
            "cutoff": cutoff,
            "deleted": deleted,
            "deleted_snapshot_files": deleted_files,
            "skipped_snapshot_files": skipped_files,
            "has_more": any(count >= limit for count in deleted.values()),
        }

    def runtime_storage_status(self, snapshot_dir: Path, *, retention_hours: int = 24) -> Dict[str, Any]:
        disk = shutil.disk_usage(self.db_path.parent)
        return {
            "database_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "disk_total_bytes": disk.total,
            "disk_used_bytes": disk.used,
            "disk_free_bytes": disk.free,
            "retention_hours": max(1, int(retention_hours)),
            "snapshot_dir": str(snapshot_dir),
        }

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

    def _rules_allowed_keys(self) -> set[str]:
        return {
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
            "fall_score_threshold",
            "fall_confirm_frames",
            "fall_confirm_seconds",
            "fall_recover_frames",
            "activity_detection_enabled",
            "fire_detection_enabled",
            "fire_event_score_threshold",
            "fire_motion_threshold",
            "fire_temporal_threshold",
            "fire_confirm_frames",
            "no_person_seconds",
            "offline_enabled",
            "notification_enabled",
        }

    def _merge_rules_patch(self, patch: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        allowed = self._rules_allowed_keys()
        current = dict(base or self.get_rules())
        next_values = {**current}
        for key, value in patch.items():
            if key in allowed and value is not None:
                next_values[key] = value
        return {key: next_values[key] for key in allowed if key in next_values}

    def merge_rules_patch(self, patch: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._merge_rules_patch(patch, base=base)

    def _device_sync_state_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["desired_rules"] = json.loads(data.pop("desired_rules_json", "{}") or "{}")
        data["desired_config"] = json.loads(data.pop("desired_config_json", "{}") or "{}")
        data["reported_status"] = json.loads(data.pop("reported_status_json", "{}") or "{}")
        return data

    def _device_rollout_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["rules_patch"] = json.loads(data.pop("rules_patch_json", "{}") or "{}")
        data["config_patch"] = json.loads(data.pop("config_patch_json", "{}") or "{}")
        data["scope_device_ids"] = json.loads(data.pop("scope_device_ids_json", "[]") or "[]")
        data["canary_device_ids"] = json.loads(data.pop("canary_device_ids_json", "[]") or "[]")
        data["applied_device_ids"] = json.loads(data.pop("applied_device_ids_json", "[]") or "[]")
        data["rolled_back_device_ids"] = json.loads(data.pop("rolled_back_device_ids_json", "[]") or "[]")
        data["previous_targets"] = json.loads(data.pop("previous_targets_json", "{}") or "{}")
        return data

    def _media_asset_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _media_upload_session_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _package_release_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _package_execution_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["output"] = json.loads(data.pop("output_json", "{}") or "{}")
        return data

    def _notification_delivery_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["response"] = json.loads(data.pop("response_json", "{}") or "{}")
        return data

    def _elder_profile_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["likes"] = json.loads(data.pop("likes_json", "[]") or "[]")
        data["dislikes"] = json.loads(data.pop("dislikes_json", "[]") or "[]")
        data["diet_notes"] = json.loads(data.pop("diet_notes_json", "[]") or "[]")
        data["health_conditions"] = json.loads(data.pop("health_conditions_json", "[]") or "[]")
        data["routine"] = json.loads(data.pop("routine_json", "{}") or "{}")
        data["emergency_contacts"] = json.loads(data.pop("emergency_contacts_json", "[]") or "[]")
        return data

    def _calendar_event_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["type"] = data.pop("event_type", "")
        data["remind_before_days"] = json.loads(data.pop("remind_before_days_json", "[]") or "[]")
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _message_candidate_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["facts"] = json.loads(data.pop("facts_json", "[]") or "[]")
        data["actions"] = json.loads(data.pop("actions_json", "[]") or "[]")
        data["source"] = json.loads(data.pop("source_json", "[]") or "[]")
        data["source_event_ids"] = json.loads(data.pop("source_event_ids_json", "[]") or "[]")
        data["source_media_ids"] = json.loads(data.pop("source_media_ids_json", "[]") or "[]")
        return data

    def _video_service_node_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["capabilities"] = json.loads(data.pop("capabilities_json", "{}") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _user_to_dict(self, row: sqlite3.Row, include_secret: bool = False) -> Dict[str, Any]:
        data = dict(row)
        if not include_secret:
            data.pop("password_salt", None)
            data.pop("password_hash", None)
        return data

    def create_user(self, email: str, password: str, display_name: str) -> Dict[str, Any]:
        normalized_email = normalize_email(email)
        clean_name = display_name.strip()
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("Email format is invalid")
        if not clean_name:
            raise ValueError("Display name is required")
        if self.get_user_by_email(normalized_email, include_secret=True):
            raise ValueError("Email already registered")
        password_salt, password_hash = hash_password(password)
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_salt, password_hash, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (normalized_email, password_salt, password_hash, clean_name, timestamp, timestamp),
            )
            user_id = int(cursor.lastrowid)
        user = self.get_user(user_id)
        if user is None:
            raise RuntimeError("User was not persisted")
        return user

    def get_user(self, user_id: int, include_secret: bool = False) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_to_dict(row, include_secret=include_secret) if row else None

    def get_user_by_email(self, email: str, include_secret: bool = False) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
        return self._user_to_dict(row, include_secret=include_secret) if row else None

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_email(email, include_secret=True)
        if user is None:
            return None
        if not verify_password(password, user["password_salt"], user["password_hash"]):
            return None
        return self.get_user(int(user["id"]))

    def create_auth_session(self, user_id: int, ttl_days: int = 30) -> Dict[str, Any]:
        timestamp = now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (timestamp,))
            conn.execute(
                """
                INSERT INTO auth_sessions (user_id, token, created_at, last_used_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, token, timestamp, timestamp, expires_at),
            )
        return {"token": token, "expires_at": expires_at, "token_type": "bearer"}

    def get_user_by_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.*
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token, timestamp),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE auth_sessions SET last_used_at = ? WHERE token = ?",
                    (timestamp, token),
                )
        return self._user_to_dict(row) if row else None

    def create_family(self, name: str, created_by: int) -> Dict[str, Any]:
        timestamp = now_iso()
        family_name = name.strip()
        if not family_name:
            raise ValueError("Family name is required")
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO families (name, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_name, created_by, timestamp, timestamp),
            )
            family_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO family_members (family_id, user_id, role, status, created_at, updated_at)
                VALUES (?, ?, 'owner', 'active', ?, ?)
                """,
                (family_id, created_by, timestamp, timestamp),
            )
        family = self.get_family(family_id, user_id=created_by)
        if family is None:
            raise RuntimeError("Family was not persisted")
        return family

    def get_elder_profile(self, family_id: int, elder_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM elder_profiles
                WHERE family_id = ? AND elder_id = ?
                LIMIT 1
                """,
                (int(family_id), str(elder_id or "").strip()),
            ).fetchone()
        return self._elder_profile_to_dict(row)

    def upsert_elder_profile(self, family_id: int, elder_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = now_iso()
        clean_elder_id = str(elder_id or "").strip()
        if not clean_elder_id:
            raise ValueError("elder_id is required")
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM elder_profiles
                WHERE family_id = ? AND elder_id = ?
                LIMIT 1
                """,
                (int(family_id), clean_elder_id),
            ).fetchone()
            params = (
                str(payload.get("display_name") or "").strip(),
                str(payload.get("relationship") or "").strip(),
                str(payload.get("city") or "").strip(),
                str(payload.get("birthday") or "").strip(),
                str(payload.get("lunar_birthday") or "").strip(),
                str(payload.get("living_status") or "").strip(),
                str(payload.get("primary_room") or "").strip(),
                json.dumps(payload.get("likes") or [], ensure_ascii=False),
                json.dumps(payload.get("dislikes") or [], ensure_ascii=False),
                json.dumps(payload.get("diet_notes") or [], ensure_ascii=False),
                json.dumps(payload.get("health_conditions") or [], ensure_ascii=False),
                str(payload.get("medication_notes") or "").strip(),
                json.dumps(payload.get("routine") or {}, ensure_ascii=False),
                json.dumps(payload.get("emergency_contacts") or [], ensure_ascii=False),
                str(payload.get("home_area") or "").strip(),
                str(payload.get("privacy_level") or "family_only").strip() or "family_only",
            )
            if row is None:
                conn.execute(
                    """
                    INSERT INTO elder_profiles (
                        family_id, elder_id, display_name, relationship, city, birthday,
                        lunar_birthday, living_status, primary_room, likes_json, dislikes_json,
                        diet_notes_json, health_conditions_json, medication_notes, routine_json,
                        emergency_contacts_json, home_area, privacy_level, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (int(family_id), clean_elder_id, *params, timestamp, timestamp),
                )
            else:
                conn.execute(
                    """
                    UPDATE elder_profiles
                    SET
                        display_name = ?,
                        relationship = ?,
                        city = ?,
                        birthday = ?,
                        lunar_birthday = ?,
                        living_status = ?,
                        primary_room = ?,
                        likes_json = ?,
                        dislikes_json = ?,
                        diet_notes_json = ?,
                        health_conditions_json = ?,
                        medication_notes = ?,
                        routine_json = ?,
                        emergency_contacts_json = ?,
                        home_area = ?,
                        privacy_level = ?,
                        updated_at = ?
                    WHERE family_id = ? AND elder_id = ?
                    """,
                    (*params, timestamp, int(family_id), clean_elder_id),
                )
        profile = self.get_elder_profile(family_id=int(family_id), elder_id=clean_elder_id)
        if profile is None:
            raise RuntimeError("Elder profile was not persisted")
        return profile

    def list_calendar_events(self, family_id: int, elder_id: str = "") -> list[Dict[str, Any]]:
        query = """
            SELECT *
            FROM calendar_events
            WHERE family_id = ?
        """
        params: list[Any] = [int(family_id)]
        clean_elder_id = str(elder_id or "").strip()
        if clean_elder_id:
            query += " AND elder_id = ?"
            params.append(clean_elder_id)
        query += " ORDER BY start_at ASC, id ASC"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [event for row in rows if (event := self._calendar_event_to_dict(row)) is not None]

    def create_calendar_event(self, family_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO calendar_events (
                    family_id, elder_id, event_type, title, start_at,
                    remind_before_days_json, source, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    str(payload.get("elder_id") or "").strip(),
                    str(payload.get("type") or "").strip(),
                    str(payload.get("title") or "").strip(),
                    str(payload.get("start_at") or "").strip(),
                    json.dumps(payload.get("remind_before_days") or [], ensure_ascii=False),
                    str(payload.get("source") or "manual").strip() or "manual",
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            event_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        event = self._calendar_event_to_dict(row)
        if event is None:
            raise RuntimeError("Calendar event was not persisted")
        return event

    def list_message_candidates(
        self,
        family_id: int,
        *,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        query = """
            SELECT *
            FROM message_candidates
            WHERE family_id = ?
        """
        params: list[Any] = [int(family_id)]
        clean_status = str(status or "").strip()
        if clean_status:
            query += " AND status = ?"
            params.append(clean_status)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [message for row in rows if (message := self._message_candidate_to_dict(row)) is not None]

    def get_message_candidate(self, family_id: int, message_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM message_candidates
                WHERE family_id = ? AND message_id = ?
                LIMIT 1
                """,
                (int(family_id), str(message_id or "").strip()),
            ).fetchone()
        return self._message_candidate_to_dict(row)

    def clear_message_candidates(self, family_id: int, elder_id: str = "") -> int:
        query = "DELETE FROM message_candidates WHERE family_id = ?"
        params: list[Any] = [int(family_id)]
        clean_elder_id = str(elder_id or "").strip()
        if clean_elder_id:
            query += " AND elder_id = ?"
            params.append(clean_elder_id)
        with self.connect() as conn:
            cursor = conn.execute(query, tuple(params))
        return int(cursor.rowcount or 0)

    def create_message_candidate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO message_candidates (
                    message_id, family_id, device_id, elder_id, message_type, priority,
                    title, subtitle, body, facts_json, image_mode, image_url, actions_json,
                    source_json, source_event_ids_json, source_media_ids_json, generated_by,
                    status, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("message_id") or "").strip(),
                    int(payload.get("family_id")),
                    str(payload.get("device_id") or "").strip(),
                    str(payload.get("elder_id") or "").strip(),
                    str(payload.get("message_type") or "").strip(),
                    str(payload.get("priority") or "warm").strip() or "warm",
                    str(payload.get("title") or "").strip(),
                    str(payload.get("subtitle") or "").strip(),
                    str(payload.get("body") or "").strip(),
                    json.dumps(payload.get("facts") or [], ensure_ascii=False),
                    str(payload.get("image_mode") or "none").strip() or "none",
                    str(payload.get("image_url") or "").strip(),
                    json.dumps(payload.get("actions") or [], ensure_ascii=False),
                    json.dumps(payload.get("source") or [], ensure_ascii=False),
                    json.dumps(payload.get("source_event_ids") or [], ensure_ascii=False),
                    json.dumps(payload.get("source_media_ids") or [], ensure_ascii=False),
                    str(payload.get("generated_by") or "").strip(),
                    str(payload.get("status") or "open").strip() or "open",
                    str(payload.get("expires_at") or "").strip() or None,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM message_candidates WHERE message_id = ? LIMIT 1",
                (str(payload.get("message_id") or "").strip(),),
            ).fetchone()
        message = self._message_candidate_to_dict(row)
        if message is None:
            raise RuntimeError("Message candidate was not persisted")
        return message

    def update_message_candidate_status(self, family_id: int, message_id: str, status: str) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        clean_message_id = str(message_id or "").strip()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE message_candidates
                SET status = ?, updated_at = ?
                WHERE family_id = ? AND message_id = ?
                """,
                (str(status or "open").strip() or "open", timestamp, int(family_id), clean_message_id),
            )
            if cursor.rowcount <= 0:
                return None
        return self.get_message_candidate(family_id=int(family_id), message_id=clean_message_id)

    def is_family_member(self, family_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM family_members
                WHERE family_id = ? AND user_id = ? AND status = 'active'
                LIMIT 1
                """,
                (family_id, user_id),
            ).fetchone()
        return row is not None

    def _device_binding_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _device_binding_code_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _device_token_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["heartbeat"] = json.loads(data.pop("last_heartbeat_json", "{}") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        data.pop("token_hash", None)
        return data

    def _app_push_token_to_dict(self, row: sqlite3.Row | None, include_secret: bool = False) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        if not include_secret:
            data.pop("push_token", None)
            data.pop("token_hash", None)
        return data

    def _expire_device_binding_codes(self, conn: sqlite3.Connection) -> None:
        timestamp = now_iso()
        conn.execute(
            """
            UPDATE device_binding_codes
            SET status = 'expired', updated_at = ?
            WHERE status = 'active' AND expires_at <= ?
            """,
            (timestamp, timestamp),
        )

    def list_family_device_bindings(self, family_id: int) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM device_bindings
                WHERE family_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (family_id,),
            ).fetchall()
        return [self._device_binding_to_dict(row) for row in rows]

    def get_device_binding(self, family_id: int, device_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM device_bindings
                WHERE family_id = ? AND device_id = ?
                LIMIT 1
                """,
                (family_id, device_id.strip()),
            ).fetchone()
        return self._device_binding_to_dict(row) if row else None

    def list_device_bindings_by_device(self, device_id: str) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM device_bindings
                WHERE device_id = ? AND status = 'active'
                ORDER BY created_at DESC, id DESC
                """,
                (device_id.strip(),),
            ).fetchall()
        return [self._device_binding_to_dict(row) for row in rows]

    def list_device_bound_family_ids(self, device_id: str) -> list[int]:
        bindings = self.list_device_bindings_by_device(device_id)
        return [int(binding["family_id"]) for binding in bindings]

    def create_device_binding(
        self,
        family_id: int,
        bound_by_user_id: int,
        device_id: str,
        device_name: str,
        device_type: str = "edge-agent",
        note: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.is_family_member(family_id, bound_by_user_id):
            raise ValueError("You are not a member of this family")
        clean_device_id = device_id.strip()
        clean_device_name = device_name.strip()
        if not clean_device_id:
            raise ValueError("Device ID is required")
        if not clean_device_name:
            raise ValueError("Device name is required")
        timestamp = now_iso()
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO device_bindings (
                        family_id, device_id, device_name, device_type, note, status,
                        bound_by_user_id, bound_at, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        family_id,
                        clean_device_id,
                        clean_device_name,
                        device_type.strip() or "edge-agent",
                        note.strip(),
                        bound_by_user_id,
                        timestamp,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                binding_id = int(cursor.lastrowid)
                row = conn.execute("SELECT * FROM device_bindings WHERE id = ?", (binding_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("This device is already bound to the family") from exc
        if row is None:
            raise RuntimeError("DeviceBinding was not persisted")
        return self._device_binding_to_dict(row)

    def create_device_binding_code(
        self,
        family_id: int,
        issued_by_user_id: int,
        expires_in_minutes: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.is_family_member(family_id, issued_by_user_id):
            raise ValueError("You are not a member of this family")
        ttl_minutes = max(1, min(int(expires_in_minutes), 60))
        issued_at = now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
        for _ in range(8):
            code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
            try:
                with self.connect() as conn:
                    self._expire_device_binding_codes(conn)
                    cursor = conn.execute(
                        """
                        INSERT INTO device_binding_codes (
                            family_id, code, status, issued_by_user_id, issued_at, expires_at,
                            metadata_json, created_at, updated_at
                        )
                        VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            family_id,
                            code,
                            issued_by_user_id,
                            issued_at,
                            expires_at,
                            json.dumps(metadata or {}, ensure_ascii=False),
                            issued_at,
                            issued_at,
                        ),
                    )
                    row = conn.execute(
                        "SELECT * FROM device_binding_codes WHERE id = ?",
                        (int(cursor.lastrowid),),
                    ).fetchone()
                if row is None:
                    raise RuntimeError("Device binding code was not persisted")
                return self._device_binding_code_to_dict(row)
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("Failed to generate a unique binding code")

    def list_device_binding_codes(self, family_id: int) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            self._expire_device_binding_codes(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM device_binding_codes
                WHERE family_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """,
                (family_id,),
            ).fetchall()
        return [self._device_binding_code_to_dict(row) for row in rows]

    def consume_device_binding_code(self, code: str, device_id: str) -> Dict[str, Any]:
        normalized_code = code.strip().upper()
        timestamp = now_iso()
        with self.connect() as conn:
            self._expire_device_binding_codes(conn)
            row = conn.execute(
                """
                SELECT *
                FROM device_binding_codes
                WHERE code = ? AND status = 'active'
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            if row is None:
                raise ValueError("Binding code is invalid or expired")
            conn.execute(
                """
                UPDATE device_binding_codes
                SET status = 'consumed', consumed_at = ?, consumed_by_device_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, device_id.strip(), timestamp, int(row["id"])),
            )
            updated = conn.execute(
                "SELECT * FROM device_binding_codes WHERE id = ?",
                (int(row["id"]),),
            ).fetchone()
        if updated is None:
            raise RuntimeError("Binding code state was not persisted")
        return self._device_binding_code_to_dict(updated)

    def issue_device_token(
        self,
        family_id: int,
        device_id: str,
        device_name: str,
        device_type: str = "edge-agent",
        issued_by_code_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        token_hash = hash_token(token)
        token_prefix = token[:8]
        timestamp = now_iso()
        clean_device_id = device_id.strip()
        clean_device_name = device_name.strip() or "edge-agent"
        clean_device_type = device_type.strip() or "edge-agent"
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM device_tokens WHERE device_id = ? LIMIT 1",
                (clean_device_id,),
            ).fetchone()
            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO device_tokens (
                        family_id, device_id, device_name, device_type, token_hash, token_prefix, status,
                        issued_by_code_id, issued_at, expires_at, last_seen_at, last_heartbeat_at,
                        last_heartbeat_ip, last_heartbeat_json, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, NULL, NULL, NULL, '{}', ?, ?, ?)
                    """,
                    (
                        family_id,
                        clean_device_id,
                        clean_device_name,
                        clean_device_type,
                        token_hash,
                        token_prefix,
                        issued_by_code_id,
                        timestamp,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                token_id = int(cursor.lastrowid)
            else:
                token_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE device_tokens
                    SET
                        family_id = ?,
                        device_name = ?,
                        device_type = ?,
                        token_hash = ?,
                        token_prefix = ?,
                        status = 'active',
                        issued_by_code_id = ?,
                        issued_at = ?,
                        expires_at = NULL,
                        last_seen_at = NULL,
                        last_heartbeat_at = NULL,
                        last_heartbeat_ip = NULL,
                        last_heartbeat_json = '{}',
                        metadata_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        family_id,
                        clean_device_name,
                        clean_device_type,
                        token_hash,
                        token_prefix,
                        issued_by_code_id,
                        timestamp,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        token_id,
                    ),
                )
            row = conn.execute("SELECT * FROM device_tokens WHERE id = ?", (token_id,)).fetchone()
        if row is None:
            raise RuntimeError("Device token was not persisted")
        data = self._device_token_to_dict(row)
        data["device_token"] = token
        data["token_type"] = "device"
        return data

    def get_active_device_token_by_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM device_tokens
                WHERE device_id = ? AND status = 'active'
                LIMIT 1
                """,
                (device_id.strip(),),
            ).fetchone()
        return self._device_token_to_dict(row) if row else None

    def upsert_app_push_token(
        self,
        *,
        family_id: int,
        user_id: int,
        app_install_id: str,
        platform: str,
        provider: str,
        push_token: str,
        device_name: str = "",
        app_version: str = "",
        environment: str = "production",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        clean_install_id = str(app_install_id or "").strip()
        clean_token = str(push_token or "").strip()
        if not clean_install_id:
            raise ValueError("app_install_id is required")
        if not clean_token:
            raise ValueError("push_token is required")
        clean_platform = str(platform or "").strip().lower() or "ios"
        clean_provider = str(provider or "").strip().lower() or "apns"
        clean_environment = str(environment or "").strip().lower() or "production"
        token_hash = hash_token(clean_token)
        token_prefix = clean_token[:8]
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM app_push_tokens
                WHERE user_id = ? AND app_install_id = ?
                LIMIT 1
                """,
                (int(user_id), clean_install_id),
            ).fetchone()
            if existing is None:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM app_push_tokens
                    WHERE token_hash = ?
                    LIMIT 1
                    """,
                    (token_hash,),
                ).fetchone()
            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO app_push_tokens (
                        family_id, user_id, app_install_id, platform, provider, push_token, token_hash, token_prefix,
                        device_name, app_version, environment, status, last_registered_at, last_seen_at,
                        metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        int(family_id),
                        int(user_id),
                        clean_install_id,
                        clean_platform,
                        clean_provider,
                        clean_token,
                        token_hash,
                        token_prefix,
                        str(device_name or "").strip(),
                        str(app_version or "").strip(),
                        clean_environment,
                        timestamp,
                        timestamp,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                token_id = int(cursor.lastrowid)
            else:
                token_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE app_push_tokens
                    SET
                        family_id = ?,
                        user_id = ?,
                        app_install_id = ?,
                        platform = ?,
                        provider = ?,
                        push_token = ?,
                        token_hash = ?,
                        token_prefix = ?,
                        device_name = ?,
                        app_version = ?,
                        environment = ?,
                        status = 'active',
                        last_registered_at = ?,
                        last_seen_at = ?,
                        metadata_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        int(family_id),
                        int(user_id),
                        clean_install_id,
                        clean_platform,
                        clean_provider,
                        clean_token,
                        token_hash,
                        token_prefix,
                        str(device_name or "").strip(),
                        str(app_version or "").strip(),
                        clean_environment,
                        timestamp,
                        timestamp,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        token_id,
                    ),
                )
            row = conn.execute("SELECT * FROM app_push_tokens WHERE id = ?", (token_id,)).fetchone()
        token_row = self._app_push_token_to_dict(row)
        if token_row is None:
            raise RuntimeError("App push token was not persisted")
        return token_row

    def list_user_app_push_tokens(self, user_id: int, family_id: Optional[int] = None) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            if family_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM app_push_tokens
                    WHERE user_id = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (int(user_id),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM app_push_tokens
                    WHERE user_id = ? AND family_id = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (int(user_id), int(family_id)),
                ).fetchall()
        return [item for item in (self._app_push_token_to_dict(row) for row in rows) if item is not None]

    def list_family_app_push_tokens(self, family_id: int, include_secret: bool = False) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM app_push_tokens
                WHERE family_id = ? AND status = 'active'
                ORDER BY updated_at DESC, id DESC
                """,
                (int(family_id),),
            ).fetchall()
        return [item for item in (self._app_push_token_to_dict(row, include_secret=include_secret) for row in rows) if item is not None]

    def deactivate_app_push_token(self, *, user_id: int, app_install_id: str) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        clean_install_id = str(app_install_id or "").strip()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE app_push_tokens
                SET status = 'revoked', updated_at = ?
                WHERE user_id = ? AND app_install_id = ?
                """,
                (timestamp, int(user_id), clean_install_id),
            )
            row = conn.execute(
                """
                SELECT *
                FROM app_push_tokens
                WHERE user_id = ? AND app_install_id = ?
                LIMIT 1
                """,
                (int(user_id), clean_install_id),
            ).fetchone()
        return self._app_push_token_to_dict(row) if row else None

    def get_device_token_by_raw_token(self, raw_token: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM device_tokens
                WHERE token_hash = ? AND status = 'active'
                LIMIT 1
                """,
                (hash_token(raw_token),),
            ).fetchone()
        return self._device_token_to_dict(row) if row else None

    def record_device_heartbeat(
        self,
        token_id: int,
        heartbeat: Optional[Dict[str, Any]] = None,
        remote_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_tokens
                SET
                    last_seen_at = ?,
                    last_heartbeat_at = ?,
                    last_heartbeat_ip = ?,
                    last_heartbeat_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    timestamp,
                    remote_ip,
                    json.dumps(heartbeat or {}, ensure_ascii=False),
                    timestamp,
                    token_id,
                ),
            )
            row = conn.execute("SELECT * FROM device_tokens WHERE id = ?", (token_id,)).fetchone()
        if row is None:
            raise RuntimeError("Heartbeat state was not persisted")
        return self._device_token_to_dict(row)

    def get_family(self, family_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        membership_join = "LEFT JOIN family_members fm ON 1 = 0"
        params: list[Any] = [family_id]
        if user_id is not None:
            membership_join = "LEFT JOIN family_members fm ON fm.family_id = f.id AND fm.user_id = ? AND fm.status = 'active'"
            params = [user_id, family_id]
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    f.*,
                    fm.role AS my_role,
                    (
                        SELECT COUNT(*)
                        FROM family_members fm2
                        WHERE fm2.family_id = f.id AND fm2.status = 'active'
                    ) AS member_count
                FROM families f
                {membership_join}
                WHERE f.id = ?
                """,
                params,
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        if user_id is not None and data.get("my_role") is None:
            return None
        data["devices"] = self.list_family_device_bindings(family_id)
        return data

    def list_user_families(self, user_id: int) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    f.*,
                    fm.role AS my_role,
                    (
                        SELECT COUNT(*)
                        FROM family_members fm2
                        WHERE fm2.family_id = f.id AND fm2.status = 'active'
                    ) AS member_count
                FROM families f
                JOIN family_members fm ON fm.family_id = f.id
                WHERE fm.user_id = ? AND fm.status = 'active'
                ORDER BY f.created_at DESC, f.id DESC
                """,
                (user_id,),
            ).fetchall()
        families = [dict(row) for row in rows]
        for family in families:
            family["devices"] = self.list_family_device_bindings(int(family["id"]))
        return families

    def list_user_family_ids(self, user_id: int) -> list[int]:
        return [int(family["id"]) for family in self.list_user_families(user_id)]

    def upsert_video_service_node(
        self,
        *,
        family_id: int,
        node_id: str,
        device_id: str = "",
        node_name: str = "",
        role: str = "origin",
        region: str = "local",
        service_url: str = "",
        media_url: str = "",
        public_base_url: str = "",
        health_status: str = "active",
        priority: int = 100,
        capabilities: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        clean_node_id = node_id.strip()
        if not clean_node_id:
            raise ValueError("node_id is required")
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM video_service_nodes
                WHERE family_id = ? AND node_id = ?
                LIMIT 1
                """,
                (family_id, clean_node_id),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO video_service_nodes (
                        family_id, node_id, device_id, node_name, role, region,
                        service_url, media_url, public_base_url, health_status, priority,
                        capabilities_json, metadata_json, last_seen_at, expires_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        family_id,
                        clean_node_id,
                        device_id.strip(),
                        node_name.strip(),
                        role.strip() or "origin",
                        region.strip() or "local",
                        service_url.strip(),
                        media_url.strip(),
                        public_base_url.strip(),
                        health_status.strip() or "active",
                        int(priority),
                        json.dumps(capabilities or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        expires_at,
                        timestamp,
                        timestamp,
                    ),
                )
                node_row_id = int(cursor.lastrowid)
            else:
                node_row_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE video_service_nodes
                    SET
                        device_id = ?,
                        node_name = ?,
                        role = ?,
                        region = ?,
                        service_url = ?,
                        media_url = ?,
                        public_base_url = ?,
                        health_status = ?,
                        priority = ?,
                        capabilities_json = ?,
                        metadata_json = ?,
                        last_seen_at = ?,
                        expires_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        device_id.strip(),
                        node_name.strip(),
                        role.strip() or "origin",
                        region.strip() or "local",
                        service_url.strip(),
                        media_url.strip(),
                        public_base_url.strip(),
                        health_status.strip() or "active",
                        int(priority),
                        json.dumps(capabilities or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp,
                        expires_at,
                        timestamp,
                        node_row_id,
                    ),
                )
            node = conn.execute("SELECT * FROM video_service_nodes WHERE id = ?", (node_row_id,)).fetchone()
        if node is None:
            raise RuntimeError("Video service node was not persisted")
        return self._video_service_node_to_dict(node)

    def get_video_service_node(self, family_id: int, node_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM video_service_nodes
                WHERE family_id = ? AND node_id = ?
                LIMIT 1
                """,
                (family_id, node_id.strip()),
            ).fetchone()
        return self._video_service_node_to_dict(row)

    def list_video_service_nodes(self, family_id: int, include_inactive: bool = False) -> list[Dict[str, Any]]:
        query = """
            SELECT *
            FROM video_service_nodes
            WHERE family_id = ?
        """
        params: list[Any] = [family_id]
        if not include_inactive:
            query += " AND health_status != 'offline'"
        query += " ORDER BY priority DESC, updated_at DESC, id DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._video_service_node_to_dict(row) for row in rows]

    def user_has_device_access(self, user_id: int, device_id: str) -> bool:
        user_family_ids = set(self.list_user_family_ids(user_id))
        if not user_family_ids:
            return False
        device_family_ids = set(self.list_device_bound_family_ids(device_id))
        if not device_family_ids:
            return False
        return bool(user_family_ids & device_family_ids)

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
        if current.get("enabled") and not next_values.get("enabled", True):
            self.close_camera_runtime_state(camera_id, reason="camera_disabled")
        return self.get_camera(camera_id)

    def delete_camera(self, camera_id: int) -> bool:
        self.close_camera_runtime_state(camera_id, reason="camera_deleted")
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

    def list_event_candidates(self, limit: int = 20, status: Optional[str] = None) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status == "active":
            where = """
                WHERE ec.status NOT IN ('suppressed', 'aggregated')
                  AND ec.event_type NOT IN ('no_motion', 'no_person')
                  AND ec.id IN (
                    SELECT MAX(latest.id)
                    FROM event_candidates latest
                    WHERE latest.status NOT IN ('suppressed', 'aggregated')
                      AND latest.event_type NOT IN ('no_motion', 'no_person')
                    GROUP BY latest.camera_id, latest.event_type
                  )
            """
        elif status:
            where = "WHERE ec.status = ?"
            params.append(status)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ec.*,
                    c.name AS camera_name,
                    c.room AS camera_room,
                    pe.summary AS promoted_event_summary,
                    pe.occurred_at AS promoted_event_occurred_at
                FROM event_candidates ec
                LEFT JOIN cameras c ON c.id = ec.camera_id
                LEFT JOIN events pe ON pe.id = ec.promoted_event_id
                {where}
                ORDER BY ec.updated_at DESC, ec.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._event_candidate_to_dict(row) for row in rows]

    def _observation_log_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        if data.get("snapshot_path"):
            data["snapshot_url"] = f"/snapshots/{data['snapshot_path']}"
        return data

    def upsert_observation_log(
        self,
        *,
        camera_id: int,
        observation_type: str,
        summary: str,
        evaluated_at: str,
        snapshot_id: Optional[int],
        detection_result_id: Optional[int],
        rule_evaluation_id: Optional[int],
        event_candidate_id: Optional[int],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_type = str(observation_type or "").strip()
        if not clean_type:
            raise ValueError("observation_type is required")
        timestamp = now_iso()
        seen_at = str(evaluated_at or "").strip() or timestamp
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM observation_logs
                WHERE camera_id = ? AND observation_type = ? AND status = 'open'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (int(camera_id), clean_type),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO observation_logs (
                        camera_id, observation_type, status, started_at, last_seen_at,
                        ended_at, duration_seconds, sample_count, last_snapshot_id,
                        last_detection_result_id, last_rule_evaluation_id, last_event_candidate_id,
                        summary, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, 'open', ?, ?, NULL, 0, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(camera_id),
                        clean_type,
                        seen_at,
                        seen_at,
                        int(snapshot_id) if snapshot_id else None,
                        int(detection_result_id) if detection_result_id else None,
                        int(rule_evaluation_id) if rule_evaluation_id else None,
                        int(event_candidate_id) if event_candidate_id else None,
                        str(summary or "").strip(),
                        json.dumps(payload or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                log_id = int(cursor.lastrowid)
            else:
                started_at = datetime.fromisoformat(str(row["started_at"]))
                last_seen_at = datetime.fromisoformat(seen_at)
                duration_seconds = max(0, int((last_seen_at - started_at).total_seconds()))
                log_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE observation_logs
                    SET
                        last_seen_at = ?,
                        duration_seconds = ?,
                        sample_count = sample_count + 1,
                        last_snapshot_id = ?,
                        last_detection_result_id = ?,
                        last_rule_evaluation_id = ?,
                        last_event_candidate_id = ?,
                        summary = ?,
                        payload_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        seen_at,
                        duration_seconds,
                        int(snapshot_id) if snapshot_id else None,
                        int(detection_result_id) if detection_result_id else None,
                        int(rule_evaluation_id) if rule_evaluation_id else None,
                        int(event_candidate_id) if event_candidate_id else None,
                        str(summary or "").strip(),
                        json.dumps(payload or {}, ensure_ascii=False),
                        timestamp,
                        log_id,
                    ),
                )
            updated = conn.execute(
                """
                SELECT
                    ol.*,
                    c.name AS camera_name,
                    c.room AS camera_room,
                    s.image_path AS snapshot_path
                FROM observation_logs ol
                LEFT JOIN cameras c ON c.id = ol.camera_id
                LEFT JOIN snapshots s ON s.id = ol.last_snapshot_id
                WHERE ol.id = ?
                """,
                (log_id,),
            ).fetchone()
        log = self._observation_log_to_dict(updated)
        if log is None:
            raise RuntimeError("Observation log was not persisted")
        return log

    def close_observation_log(
        self,
        *,
        camera_id: int,
        observation_type: str,
        ended_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        clean_type = str(observation_type or "").strip()
        timestamp = now_iso()
        end_time = str(ended_at or "").strip() or timestamp
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM observation_logs
                WHERE camera_id = ? AND observation_type = ? AND status = 'open'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (int(camera_id), clean_type),
            ).fetchone()
            if row is None:
                return None
            started_at = datetime.fromisoformat(str(row["started_at"]))
            ended = datetime.fromisoformat(end_time)
            duration_seconds = max(0, int((ended - started_at).total_seconds()))
            conn.execute(
                """
                UPDATE observation_logs
                SET status = 'closed', ended_at = ?, duration_seconds = ?, updated_at = ?
                WHERE id = ?
                """,
                (end_time, duration_seconds, timestamp, int(row["id"])),
            )
            updated = conn.execute("SELECT * FROM observation_logs WHERE id = ?", (int(row["id"]),)).fetchone()
        return self._observation_log_to_dict(updated)

    def list_observation_logs(
        self,
        *,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE ol.status = ?"
            params.append(status)
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ol.*,
                    c.name AS camera_name,
                    c.room AS camera_room,
                    s.image_path AS snapshot_path
                FROM observation_logs ol
                LEFT JOIN cameras c ON c.id = ol.camera_id
                LEFT JOIN snapshots s ON s.id = ol.last_snapshot_id
                {where}
                ORDER BY ol.updated_at DESC, ol.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [log for row in rows if (log := self._observation_log_to_dict(row)) is not None]

    def _presence_session_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        return data

    def upsert_presence_session(
        self,
        *,
        camera_id: int,
        observed_at: str,
        person_count: int,
        snapshot_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        seen_at = str(observed_at or "").strip() or timestamp
        count = max(1, int(person_count or 1))
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM presence_sessions
                WHERE camera_id = ? AND status = 'open'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (int(camera_id),),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO presence_sessions (
                        camera_id, status, started_at, last_seen_at, ended_at,
                        duration_seconds, sample_count, max_person_count,
                        representative_snapshot_id, close_reason, payload_json,
                        created_at, updated_at
                    )
                    VALUES (?, 'open', ?, ?, NULL, 0, 1, ?, ?, '', ?, ?, ?)
                    """,
                    (
                        int(camera_id),
                        seen_at,
                        seen_at,
                        count,
                        int(snapshot_id) if snapshot_id else None,
                        json.dumps(payload or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                session_id = int(cursor.lastrowid)
            else:
                started_at = datetime.fromisoformat(str(row["started_at"]))
                last_seen_at = datetime.fromisoformat(seen_at)
                duration_seconds = max(0, int((last_seen_at - started_at).total_seconds()))
                session_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE presence_sessions
                    SET last_seen_at = ?, duration_seconds = ?, sample_count = sample_count + 1,
                        max_person_count = MAX(max_person_count, ?),
                        representative_snapshot_id = COALESCE(?, representative_snapshot_id),
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        seen_at,
                        duration_seconds,
                        count,
                        int(snapshot_id) if snapshot_id else None,
                        json.dumps(payload or {}, ensure_ascii=False),
                        timestamp,
                        session_id,
                    ),
                )
            updated = conn.execute("SELECT * FROM presence_sessions WHERE id = ?", (session_id,)).fetchone()
        session = self._presence_session_to_dict(updated)
        if session is None:
            raise RuntimeError("Presence session was not persisted")
        return session

    def close_presence_session(
        self,
        *,
        camera_id: int,
        ended_at: Optional[str] = None,
        reason: str = "person_not_visible",
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        end_time = str(ended_at or "").strip() or timestamp
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM presence_sessions
                WHERE camera_id = ? AND status = 'open'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (int(camera_id),),
            ).fetchone()
            if row is None:
                return None
            started_at = datetime.fromisoformat(str(row["started_at"]))
            ended = datetime.fromisoformat(end_time)
            duration_seconds = max(0, int((ended - started_at).total_seconds()))
            conn.execute(
                """
                UPDATE presence_sessions
                SET status = 'closed', ended_at = ?, duration_seconds = ?,
                    close_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (end_time, duration_seconds, str(reason or ""), timestamp, int(row["id"])),
            )
            updated = conn.execute("SELECT * FROM presence_sessions WHERE id = ?", (int(row["id"]),)).fetchone()
        return self._presence_session_to_dict(updated)

    def list_presence_sessions(self, *, limit: int = 50, status: Optional[str] = None) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE status = ?"
            params.append(str(status))
        params.append(max(1, min(int(limit), 500)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM presence_sessions
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [item for row in rows if (item := self._presence_session_to_dict(row)) is not None]

    def _posture_episode_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["normal_lying_zone"] = bool(data.get("normal_lying_zone"))
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        return data

    def upsert_posture_episode(
        self,
        *,
        camera_id: int,
        track_id: str,
        posture: str,
        started_at: str,
        confirmed_at: str,
        last_seen_at: str,
        sample_count: int,
        mean_confidence: float,
        max_confidence: float,
        normal_lying_zone: bool = False,
        scene_zone_id: Any = None,
        scene_zone_label: Any = None,
        snapshot_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        clean_track_id = str(track_id or "").strip()
        clean_posture = str(posture or "unknown").strip()
        if not clean_track_id:
            raise ValueError("track_id is required")
        start_time = str(started_at or "").strip() or timestamp
        confirm_time = str(confirmed_at or "").strip() or start_time
        seen_time = str(last_seen_at or "").strip() or timestamp
        duration_seconds = max(0, int((datetime.fromisoformat(seen_time) - datetime.fromisoformat(start_time)).total_seconds()))
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE posture_episodes
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = 'posture_changed', updated_at = ?
                WHERE camera_id = ? AND track_id = ? AND status = 'open' AND posture != ?
                """,
                (seen_time, seen_time, timestamp, int(camera_id), clean_track_id, clean_posture),
            )
            row = conn.execute(
                """
                SELECT * FROM posture_episodes
                WHERE camera_id = ? AND track_id = ? AND posture = ? AND status = 'open'
                ORDER BY id DESC LIMIT 1
                """,
                (int(camera_id), clean_track_id, clean_posture),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO posture_episodes (
                        camera_id, track_id, posture, status, started_at, confirmed_at,
                        last_seen_at, ended_at, duration_seconds, sample_count,
                        mean_confidence, max_confidence, normal_lying_zone,
                        scene_zone_id, scene_zone_label, representative_snapshot_id,
                        close_reason, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'open', ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
                    """,
                    (
                        int(camera_id), clean_track_id, clean_posture, start_time, confirm_time,
                        seen_time, duration_seconds, max(1, int(sample_count)),
                        float(mean_confidence or 0.0), float(max_confidence or 0.0),
                        1 if normal_lying_zone else 0,
                        str(scene_zone_id) if scene_zone_id not in (None, "") else None,
                        str(scene_zone_label) if scene_zone_label not in (None, "") else None,
                        int(snapshot_id) if snapshot_id else None,
                        json.dumps(payload or {}, ensure_ascii=False), timestamp, timestamp,
                    ),
                )
                episode_id = int(cursor.lastrowid)
            else:
                episode_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE posture_episodes
                    SET last_seen_at = ?, duration_seconds = ?, sample_count = ?,
                        mean_confidence = ?, max_confidence = ?, normal_lying_zone = ?,
                        scene_zone_id = ?, scene_zone_label = ?,
                        representative_snapshot_id = COALESCE(?, representative_snapshot_id),
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        seen_time, duration_seconds, max(1, int(sample_count)),
                        float(mean_confidence or 0.0), float(max_confidence or 0.0),
                        1 if normal_lying_zone else 0,
                        str(scene_zone_id) if scene_zone_id not in (None, "") else None,
                        str(scene_zone_label) if scene_zone_label not in (None, "") else None,
                        int(snapshot_id) if snapshot_id else None,
                        json.dumps(payload or {}, ensure_ascii=False), timestamp, episode_id,
                    ),
                )
            updated = conn.execute("SELECT * FROM posture_episodes WHERE id = ?", (episode_id,)).fetchone()
        episode = self._posture_episode_to_dict(updated)
        if episode is None:
            raise RuntimeError("Posture episode was not persisted")
        return episode

    def close_posture_episode(
        self,
        *,
        camera_id: int,
        track_id: Optional[str] = None,
        posture: Optional[str] = None,
        ended_at: Optional[str] = None,
        reason: str = "track_expired",
    ) -> int:
        timestamp = now_iso()
        end_time = str(ended_at or "").strip() or timestamp
        clauses = ["camera_id = ?", "status = 'open'"]
        params: list[Any] = [int(camera_id)]
        if track_id:
            clauses.append("track_id = ?")
            params.append(str(track_id))
        if posture:
            clauses.append("posture = ?")
            params.append(str(posture))
        params = [end_time, end_time, str(reason or ""), timestamp, *params]
        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE posture_episodes
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = ?, updated_at = ?
                WHERE {' AND '.join(clauses)}
                """,
                tuple(params),
            )
        return int(cursor.rowcount or 0)

    def list_posture_episodes(self, *, limit: int = 100, status: Optional[str] = None) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE pe.status = ?"
            params.append(str(status))
        params.append(max(1, min(int(limit), 1000)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT pe.*, c.name AS camera_name, c.room AS camera_room
                FROM posture_episodes pe
                LEFT JOIN cameras c ON c.id = pe.camera_id
                {where}
                ORDER BY pe.updated_at DESC, pe.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [item for row in rows if (item := self._posture_episode_to_dict(row)) is not None]

    def close_camera_runtime_state(self, camera_id: int, *, reason: str) -> Dict[str, int]:
        timestamp = now_iso()
        with self.connect() as conn:
            observation_cursor = conn.execute(
                """
                UPDATE observation_logs
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    updated_at = ?
                WHERE camera_id = ? AND status = 'open'
                """,
                (timestamp, timestamp, timestamp, int(camera_id)),
            )
            presence_cursor = conn.execute(
                """
                UPDATE presence_sessions
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = ?, updated_at = ?
                WHERE camera_id = ? AND status = 'open'
                """,
                (timestamp, timestamp, str(reason or ""), timestamp, int(camera_id)),
            )
            posture_cursor = conn.execute(
                """
                UPDATE posture_episodes
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = ?, updated_at = ?
                WHERE camera_id = ? AND status = 'open'
                """,
                (timestamp, timestamp, str(reason or ""), timestamp, int(camera_id)),
            )
        return {
            "observation_logs_closed": int(observation_cursor.rowcount or 0),
            "presence_sessions_closed": int(presence_cursor.rowcount or 0),
            "posture_episodes_closed": int(posture_cursor.rowcount or 0),
        }

    def reconcile_camera_runtime_state(self) -> Dict[str, int]:
        timestamp = now_iso()
        with self.connect() as conn:
            observation_cursor = conn.execute(
                """
                UPDATE observation_logs
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    updated_at = ?
                WHERE status = 'open'
                  AND NOT EXISTS (SELECT 1 FROM cameras c WHERE c.id = observation_logs.camera_id)
                """,
                (timestamp, timestamp, timestamp),
            )
            presence_cursor = conn.execute(
                """
                UPDATE presence_sessions
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = 'camera_missing', updated_at = ?
                WHERE status = 'open'
                  AND NOT EXISTS (SELECT 1 FROM cameras c WHERE c.id = presence_sessions.camera_id)
                """,
                (timestamp, timestamp, timestamp),
            )
            posture_cursor = conn.execute(
                """
                UPDATE posture_episodes
                SET status = 'closed', ended_at = ?,
                    duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                    close_reason = 'camera_missing', updated_at = ?
                WHERE status = 'open'
                  AND NOT EXISTS (SELECT 1 FROM cameras c WHERE c.id = posture_episodes.camera_id)
                """,
                (timestamp, timestamp, timestamp),
            )
        return {
            "orphan_observation_logs_closed": int(observation_cursor.rowcount or 0),
            "orphan_presence_sessions_closed": int(presence_cursor.rowcount or 0),
            "orphan_posture_episodes_closed": int(posture_cursor.rowcount or 0),
        }

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

    def get_snapshot_by_path(self, image_path: str) -> Optional[Dict[str, Any]]:
        clean_path = str(image_path or "").strip().lstrip("/")
        if not clean_path:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE image_path = ? ORDER BY captured_at DESC, id DESC LIMIT 1",
                (clean_path,),
            ).fetchone()
        return self._snapshot_to_dict(row) if row else None

    def get_media_asset(self, asset_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM media_assets WHERE id = ? LIMIT 1", (int(asset_id),)).fetchone()
        return self._media_asset_to_dict(row)

    def get_media_asset_by_snapshot(self, snapshot_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE snapshot_id = ? LIMIT 1",
                (int(snapshot_id),),
            ).fetchone()
        return self._media_asset_to_dict(row)

    def get_media_asset_by_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE event_id = ? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
                (int(event_id),),
            ).fetchone()
        return self._media_asset_to_dict(row)

    def get_media_asset_by_source_path(self, snapshot_path: str) -> Optional[Dict[str, Any]]:
        clean_path = str(snapshot_path or "").strip().lstrip("/")
        if not clean_path:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE source_snapshot_path = ? LIMIT 1",
                (clean_path,),
            ).fetchone()
        return self._media_asset_to_dict(row)

    def get_media_asset_by_object_key(self, object_key: str) -> Optional[Dict[str, Any]]:
        clean_key = str(object_key or "").strip().lstrip("/")
        if not clean_key:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE object_key = ? LIMIT 1",
                (clean_key,),
            ).fetchone()
        return self._media_asset_to_dict(row)

    def attach_media_asset_to_event(self, asset_id: int, event_id: int) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE media_assets
                SET event_id = ?, uploaded_at = COALESCE(uploaded_at, ?)
                WHERE id = ?
                """,
                (int(event_id), timestamp, int(asset_id)),
            )
            row = conn.execute("SELECT * FROM media_assets WHERE id = ? LIMIT 1", (int(asset_id),)).fetchone()
        return self._media_asset_to_dict(row)

    def create_media_asset(
        self,
        *,
        family_id: int,
        device_id: str,
        snapshot_id: Optional[int],
        source_snapshot_path: str,
        object_key: str,
        content_type: str = "image/jpeg",
        byte_size: int = 0,
        checksum_sha256: str = "",
        provider: str = "localfs",
        bucket: str = "local",
        event_id: Optional[int] = None,
        status: str = "uploaded",
        metadata: Optional[Dict[str, Any]] = None,
        uploaded_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_path = str(source_snapshot_path or "").strip().lstrip("/")
        if not clean_path:
            raise ValueError("source_snapshot_path is required")
        existing = self.get_media_asset_by_source_path(clean_path)
        if existing is not None:
            if event_id and not existing.get("event_id"):
                with self.connect() as conn:
                    conn.execute("UPDATE media_assets SET event_id = ? WHERE id = ?", (int(event_id), int(existing["id"])))
                existing = self.get_media_asset(int(existing["id"]))
            if existing is None:
                raise RuntimeError("Media asset was not persisted")
            return existing
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO media_assets (
                    family_id, device_id, event_id, snapshot_id, source_snapshot_path,
                    provider, bucket, object_key, content_type, byte_size,
                    checksum_sha256, status, metadata_json, created_at, uploaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    str(device_id or "").strip(),
                    int(event_id) if event_id else None,
                    int(snapshot_id) if snapshot_id else None,
                    clean_path,
                    provider,
                    bucket,
                    str(object_key or "").strip(),
                    str(content_type or "image/jpeg").strip() or "image/jpeg",
                    max(0, int(byte_size or 0)),
                    str(checksum_sha256 or "").strip(),
                    str(status or "uploaded").strip() or "uploaded",
                    json.dumps(metadata or {}, ensure_ascii=False),
                    timestamp,
                    uploaded_at or timestamp,
                ),
            )
            asset_id = int(cursor.lastrowid)
        asset = self.get_media_asset(asset_id)
        if asset is None:
            raise RuntimeError("Media asset was not persisted")
        return asset

    def create_media_upload_session(
        self,
        *,
        family_id: int,
        created_by_user_id: int,
        object_key: str,
        upload_token_hash: str,
        expires_at: str,
        file_name: str = "",
        content_type: str = "application/octet-stream",
        byte_size: int = 0,
        provider: str = "signed-localfs",
        bucket: str = "public-media",
        device_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO media_upload_sessions (
                    family_id, created_by_user_id, device_id, file_name, content_type,
                    byte_size, provider, bucket, object_key, upload_token_hash,
                    status, metadata_json, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    int(created_by_user_id),
                    str(device_id or "").strip(),
                    str(file_name or "").strip(),
                    str(content_type or "application/octet-stream").strip() or "application/octet-stream",
                    max(0, int(byte_size or 0)),
                    str(provider or "signed-localfs").strip() or "signed-localfs",
                    str(bucket or "public-media").strip() or "public-media",
                    str(object_key or "").strip(),
                    str(upload_token_hash or "").strip(),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    str(expires_at or "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            session_id = int(cursor.lastrowid)
        session = self.get_media_upload_session(session_id)
        if session is None:
            raise RuntimeError("Media upload session was not persisted")
        return session

    def get_media_upload_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_upload_sessions WHERE id = ? LIMIT 1",
                (int(session_id),),
            ).fetchone()
        return self._media_upload_session_to_dict(row)

    def get_media_upload_session_by_token_hash(self, upload_token_hash: str) -> Optional[Dict[str, Any]]:
        clean_hash = str(upload_token_hash or "").strip()
        if not clean_hash:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_upload_sessions WHERE upload_token_hash = ? LIMIT 1",
                (clean_hash,),
            ).fetchone()
        return self._media_upload_session_to_dict(row)

    def mark_media_upload_session_uploaded(
        self,
        session_id: int,
        *,
        byte_size: int,
        content_type: str = "",
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE media_upload_sessions
                SET status = 'uploaded',
                    byte_size = ?,
                    content_type = CASE WHEN ? = '' THEN content_type ELSE ? END,
                    uploaded_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    max(0, int(byte_size or 0)),
                    str(content_type or "").strip(),
                    str(content_type or "").strip(),
                    timestamp,
                    timestamp,
                    int(session_id),
                ),
            )
        session = self.get_media_upload_session(int(session_id))
        if session is None:
            raise RuntimeError("Media upload session missing after upload")
        return session

    def complete_media_upload_session(
        self,
        session_id: int,
        *,
        asset_id: int,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE media_upload_sessions
                SET status = 'completed',
                    asset_id = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (int(asset_id), timestamp, timestamp, int(session_id)),
            )
        session = self.get_media_upload_session(int(session_id))
        if session is None:
            raise RuntimeError("Media upload session missing after completion")
        return session

    def create_package_release(
        self,
        *,
        family_id: int,
        package_type: str,
        version: str,
        asset_id: int,
        install_strategy: str = "file",
        entry_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_by_user_id: int,
        status: str = "active",
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO package_releases (
                    family_id, package_type, version, asset_id, install_strategy,
                    entry_path, metadata_json, status, created_by_user_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    str(package_type or "").strip(),
                    str(version or "").strip(),
                    int(asset_id),
                    str(install_strategy or "file").strip() or "file",
                    str(entry_path or "").strip(),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    str(status or "active").strip() or "active",
                    int(created_by_user_id),
                    timestamp,
                    timestamp,
                ),
            )
            release_id = int(cursor.lastrowid)
        release = self.get_package_release(release_id)
        if release is None:
            raise RuntimeError("Package release was not persisted")
        return release

    def get_package_release(self, release_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM package_releases WHERE id = ? LIMIT 1",
                (int(release_id),),
            ).fetchone()
        return self._package_release_to_dict(row)

    def get_package_release_by_version(self, family_id: int, package_type: str, version: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM package_releases
                WHERE family_id = ? AND package_type = ? AND version = ? AND status = 'active'
                LIMIT 1
                """,
                (int(family_id), str(package_type or "").strip(), str(version or "").strip()),
            ).fetchone()
        return self._package_release_to_dict(row)

    def list_package_releases(
        self,
        family_id: int,
        package_type: str = "",
        limit: int = 20,
    ) -> list[Dict[str, Any]]:
        query = """
            SELECT *
            FROM package_releases
            WHERE family_id = ?
        """
        params: list[Any] = [int(family_id)]
        clean_type = str(package_type or "").strip()
        if clean_type:
            query += " AND package_type = ?"
            params.append(clean_type)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [release for row in rows if (release := self._package_release_to_dict(row)) is not None]

    def create_package_execution(
        self,
        *,
        family_id: int,
        device_id: str,
        package_type: str,
        target_version: str,
        release_id: Optional[int] = None,
        status: str = "pending",
        staged_path: str = "",
        installed_path: str = "",
        output: Optional[Dict[str, Any]] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO package_executions (
                    family_id, device_id, package_type, target_version, release_id,
                    status, staged_path, installed_path, output_json,
                    started_at, finished_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    str(device_id or "").strip(),
                    str(package_type or "").strip(),
                    str(target_version or "").strip(),
                    int(release_id) if release_id else None,
                    str(status or "pending").strip() or "pending",
                    str(staged_path or "").strip(),
                    str(installed_path or "").strip(),
                    json.dumps(output or {}, ensure_ascii=False),
                    started_at,
                    finished_at,
                    timestamp,
                    timestamp,
                ),
            )
            execution_id = int(cursor.lastrowid)
        execution = self.get_package_execution(execution_id)
        if execution is None:
            raise RuntimeError("Package execution was not persisted")
        return execution

    def update_package_execution(
        self,
        execution_id: int,
        *,
        status: Optional[str] = None,
        staged_path: Optional[str] = None,
        installed_path: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.get_package_execution(execution_id)
        if current is None:
            raise RuntimeError("Package execution does not exist")
        next_output = dict(current.get("output") or {})
        if output:
            next_output.update(output)
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE package_executions
                SET status = ?,
                    staged_path = ?,
                    installed_path = ?,
                    output_json = ?,
                    started_at = COALESCE(?, started_at),
                    finished_at = COALESCE(?, finished_at),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(status or current.get("status") or "pending"),
                    str(staged_path if staged_path is not None else current.get("staged_path") or ""),
                    str(installed_path if installed_path is not None else current.get("installed_path") or ""),
                    json.dumps(next_output, ensure_ascii=False),
                    started_at,
                    finished_at,
                    timestamp,
                    int(execution_id),
                ),
            )
        updated = self.get_package_execution(execution_id)
        if updated is None:
            raise RuntimeError("Package execution missing after update")
        return updated

    def get_package_execution(self, execution_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM package_executions WHERE id = ? LIMIT 1",
                (int(execution_id),),
            ).fetchone()
        return self._package_execution_to_dict(row)

    def list_package_executions(
        self,
        family_id: int,
        device_id: str = "",
        limit: int = 20,
    ) -> list[Dict[str, Any]]:
        query = """
            SELECT *
            FROM package_executions
            WHERE family_id = ?
        """
        params: list[Any] = [int(family_id)]
        clean_device_id = str(device_id or "").strip()
        if clean_device_id:
            query += " AND device_id = ?"
            params.append(clean_device_id)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [execution for row in rows if (execution := self._package_execution_to_dict(row)) is not None]

    def get_latest_package_execution(
        self,
        *,
        family_id: int,
        device_id: str,
        package_type: str,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM package_executions
                WHERE family_id = ? AND device_id = ? AND package_type = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (int(family_id), str(device_id or "").strip(), str(package_type or "").strip()),
            ).fetchone()
        return self._package_execution_to_dict(row)

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
        occurred_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        event_occurred_at = str(occurred_at or "").strip() or now_iso()
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
                    event_occurred_at,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            event_id = int(cursor.lastrowid)
        event = self.get_event(event_id)
        if event is None:
            raise RuntimeError("Event was not persisted")
        return event

    def _upload_job_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        return data

    def enqueue_upload_job(
        self,
        *,
        job_type: str,
        object_type: str,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 100,
        family_id: Optional[int] = None,
        device_id: str = "",
        event_id: Optional[int] = None,
        snapshot_id: Optional[int] = None,
        camera_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        clean_key = str(idempotency_key or "").strip()
        clean_type = str(job_type or "").strip()
        if not clean_key:
            raise ValueError("idempotency_key is required")
        if not clean_type:
            raise ValueError("job_type is required")
        timestamp = now_iso()
        with self.connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO upload_jobs (
                        job_type, object_type, status, priority, idempotency_key,
                        family_id, device_id, event_id, snapshot_id, camera_id,
                        payload_json, attempt_count, last_error, next_attempt_at,
                        created_at, updated_at, completed_at
                    )
                    VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, 0, '', NULL, ?, ?, NULL)
                    """,
                    (
                        clean_type,
                        str(object_type or "").strip(),
                        int(priority),
                        clean_key,
                        int(family_id) if family_id else None,
                        str(device_id or "").strip(),
                        int(event_id) if event_id else None,
                        int(snapshot_id) if snapshot_id else None,
                        int(camera_id) if camera_id else None,
                        json.dumps(payload or {}, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                job_id = int(cursor.lastrowid)
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT * FROM upload_jobs WHERE idempotency_key = ? LIMIT 1",
                    (clean_key,),
                ).fetchone()
                job = self._upload_job_to_dict(row)
                if job is None:
                    raise RuntimeError("Upload job dedupe failed")
                return job
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        job = self._upload_job_to_dict(row)
        if job is None:
            raise RuntimeError("Upload job was not persisted")
        return job

    def enqueue_event_upload_jobs(self, event: Dict[str, Any]) -> list[Dict[str, Any]]:
        event_id = int(event["id"])
        camera_id = int(event["camera_id"]) if event.get("camera_id") else None
        snapshot_id = int(event["snapshot_id"]) if event.get("snapshot_id") else None
        base_payload = {
            "schema_version": "gohome-upload-job-v1",
            "event_id": event_id,
            "event_type": event.get("type"),
            "summary": event.get("summary"),
            "level": event.get("level"),
            "room": event.get("room") or "",
            "camera_id": camera_id,
            "snapshot_id": snapshot_id,
            "snapshot_path": event.get("snapshot_path") or "",
            "occurred_at": event.get("occurred_at"),
            "payload": event.get("payload") or {},
        }
        validation = base_payload["payload"].get("validation") if isinstance(base_payload["payload"], dict) else {}
        evidence_purpose = "validation_evidence" if isinstance(validation, dict) and validation.get("test_event") else "event_evidence"
        jobs = [
            self.enqueue_upload_job(
                job_type="event_upload",
                object_type="event",
                idempotency_key=f"event:{event_id}",
                priority=10 if event.get("level") == "critical" else 50,
                event_id=event_id,
                snapshot_id=snapshot_id,
                camera_id=camera_id,
                payload={
                    **base_payload,
                    "target": "app_server",
                    "endpoint": "/api/v1/device/events",
                },
            )
        ]
        if snapshot_id:
            jobs.append(
                self.enqueue_upload_job(
                    job_type="media_upload",
                    object_type="snapshot",
                    idempotency_key=f"snapshot:{snapshot_id}:event:{event_id}",
                    priority=5 if event.get("level") == "critical" else 40,
                    event_id=event_id,
                    snapshot_id=snapshot_id,
                    camera_id=camera_id,
                    payload={
                        **base_payload,
                        "target": "object_storage",
                        "content_type": "image/jpeg",
                        "purpose": evidence_purpose,
                    },
                )
            )
        return jobs

    def list_upload_jobs(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("uj.status = ?")
            params.append(status)
        if job_type:
            where.append("uj.job_type = ?")
            params.append(job_type)
        params.append(max(1, min(int(limit), 500)))
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    uj.*,
                    e.type AS event_type,
                    e.summary AS event_summary,
                    e.level AS event_level,
                    s.image_path AS snapshot_path,
                    c.name AS camera_name,
                    c.room AS camera_room
                FROM upload_jobs uj
                LEFT JOIN events e ON e.id = uj.event_id
                LEFT JOIN snapshots s ON s.id = uj.snapshot_id
                LEFT JOIN cameras c ON c.id = uj.camera_id
                {where_clause}
                ORDER BY
                    CASE uj.status
                        WHEN 'pending' THEN 0
                        WHEN 'failed' THEN 1
                        WHEN 'uploading' THEN 2
                        WHEN 'completed' THEN 3
                        ELSE 4
                    END,
                    uj.priority ASC,
                    uj.created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [job for row in rows if (job := self._upload_job_to_dict(row)) is not None]

    def claim_next_upload_job(self) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM upload_jobs
                WHERE status IN ('pending', 'failed')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (timestamp,),
            ).fetchone()
            if row is None:
                return None
            job_id = int(row["id"])
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'uploading',
                    attempt_count = attempt_count + 1,
                    last_error = '',
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, job_id),
            )
            claimed = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
        return self._upload_job_to_dict(claimed)

    def complete_upload_job(self, job_id: int, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
            job = self._upload_job_to_dict(row)
            if job is None:
                return None
            payload = dict(job.get("payload") or {})
            payload["upload_result"] = result
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'completed',
                    payload_json = ?,
                    last_error = '',
                    next_attempt_at = NULL,
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (json.dumps(payload, ensure_ascii=False), timestamp, timestamp, int(job_id)),
            )
            updated = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
        return self._upload_job_to_dict(updated)

    def fail_upload_job(self, job_id: int, error: str, *, retry_after_seconds: int = 60) -> Optional[Dict[str, Any]]:
        from datetime import datetime, timedelta, timezone

        timestamp = now_iso()
        next_attempt_at = (datetime.now(timezone.utc) + timedelta(seconds=max(5, int(retry_after_seconds)))).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'failed',
                    last_error = ?,
                    next_attempt_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(error or "")[:1000], next_attempt_at, timestamp, int(job_id)),
            )
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
        return self._upload_job_to_dict(row)

    def latest_completed_upload_job(
        self,
        *,
        event_id: int,
        job_type: str,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM upload_jobs
                WHERE event_id = ? AND job_type = ? AND status = 'completed'
                ORDER BY completed_at DESC, updated_at DESC
                LIMIT 1
                """,
                (int(event_id), str(job_type or "").strip()),
            ).fetchone()
        return self._upload_job_to_dict(row)

    def upload_queue_summary(self) -> Dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM upload_jobs
                GROUP BY status
                """
            ).fetchall()
            pending_critical = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_jobs uj
                JOIN events e ON e.id = uj.event_id
                WHERE uj.status IN ('pending', 'failed') AND e.level = 'critical'
                """
            ).fetchone()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        return {
            "pending": counts.get("pending", 0),
            "uploading": counts.get("uploading", 0),
            "failed": counts.get("failed", 0),
            "completed": counts.get("completed", 0),
            "pending_critical": int(pending_critical["count"] if pending_critical else 0),
            "total": sum(counts.values()),
        }

    def update_upload_job_status(
        self,
        job_id: int,
        *,
        status: str,
        last_error: str = "",
    ) -> Optional[Dict[str, Any]]:
        normalized = str(status or "").strip()
        if normalized not in {"pending", "uploading", "completed", "failed"}:
            raise ValueError("Unsupported upload job status")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE upload_jobs
                SET
                    status = ?,
                    last_error = ?,
                    attempt_count = attempt_count + CASE WHEN ? IN ('failed', 'uploading') THEN 1 ELSE 0 END,
                    updated_at = ?,
                    completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END
                WHERE id = ?
                """,
                (normalized, str(last_error or ""), normalized, timestamp, normalized, timestamp, int(job_id)),
            )
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (int(job_id),)).fetchone()
        return self._upload_job_to_dict(row)

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

    def create_notification_delivery(
        self,
        *,
        family_id: int,
        channel: str,
        title: str,
        body: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        event_id: Optional[int] = None,
        recipient: str = "",
        delivered_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notification_deliveries (
                    family_id, event_id, channel, title, body, recipient,
                    status, response_json, created_at, delivered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    int(event_id) if event_id else None,
                    str(channel or "").strip() or "unknown",
                    str(title or "").strip(),
                    str(body or "").strip(),
                    str(recipient or "").strip(),
                    str(status or "pending").strip() or "pending",
                    json.dumps(response or {}, ensure_ascii=False),
                    timestamp,
                    delivered_at,
                ),
            )
            delivery_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM notification_deliveries WHERE id = ?", (delivery_id,)).fetchone()
        delivery = self._notification_delivery_to_dict(row)
        if delivery is None:
            raise RuntimeError("Notification delivery was not persisted")
        return delivery

    def list_notification_deliveries(self, family_id: int, limit: int = 20) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM notification_deliveries
                WHERE family_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (int(family_id), max(1, min(int(limit), 100))),
            ).fetchall()
        return [self._notification_delivery_to_dict(row) for row in rows if row is not None]

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

    def get_event_ingest(self, device_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        clean_device_id = str(device_id or "").strip()
        clean_key = str(idempotency_key or "").strip()
        if not clean_device_id or not clean_key:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM event_ingests
                WHERE device_id = ? AND idempotency_key = ?
                LIMIT 1
                """,
                (clean_device_id, clean_key),
            ).fetchone()
        return dict(row) if row else None

    def bind_event_ingest(self, device_id: str, idempotency_key: str, event_id: int) -> Dict[str, Any]:
        timestamp = now_iso()
        clean_device_id = str(device_id or "").strip()
        clean_key = str(idempotency_key or "").strip()
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO event_ingests (device_id, idempotency_key, event_id, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (clean_device_id, clean_key, int(event_id), timestamp),
                )
            except sqlite3.IntegrityError:
                pass
            row = conn.execute(
                """
                SELECT *
                FROM event_ingests
                WHERE device_id = ? AND idempotency_key = ?
                LIMIT 1
                """,
                (clean_device_id, clean_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("Event ingest was not persisted")
        return dict(row)

    def get_device_sync_state(self, device_id: str) -> Optional[Dict[str, Any]]:
        clean_device_id = str(device_id or "").strip()
        if not clean_device_id:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (clean_device_id,),
            ).fetchone()
        return self._device_sync_state_to_dict(row)

    def ensure_device_sync_state(self, device_id: str, family_id: int) -> Dict[str, Any]:
        clean_device_id = str(device_id or "").strip()
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (clean_device_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO device_sync_states (
                        device_id, family_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (clean_device_id, int(family_id), timestamp, timestamp),
                )
            else:
                conn.execute(
                    """
                    UPDATE device_sync_states
                    SET family_id = ?, updated_at = ?
                    WHERE device_id = ?
                    """,
                    (int(family_id), timestamp, clean_device_id),
                )
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (clean_device_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device sync state was not persisted")
        return self._device_sync_state_to_dict(row)  # type: ignore[return-value]

    def update_device_sync_target(
        self,
        *,
        device_id: str,
        family_id: int,
        desired_app_version: str = "",
        desired_model_version: str = "",
        rules_patch: Optional[Dict[str, Any]] = None,
        config_patch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current_state = self.ensure_device_sync_state(device_id, family_id)
        desired_rules = dict(current_state.get("desired_rules") or self.get_rules())
        desired_config = dict(current_state.get("desired_config") or {})
        if rules_patch:
            desired_rules = self._merge_rules_patch(rules_patch, base=desired_rules)
        if config_patch:
            desired_config.update({key: value for key, value in config_patch.items() if value is not None})
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_sync_states
                SET
                    family_id = ?,
                    desired_app_version = ?,
                    desired_model_version = ?,
                    desired_rules_json = ?,
                    desired_rule_version = ?,
                    desired_config_json = ?,
                    desired_config_version = ?,
                    updated_at = ?
                WHERE device_id = ?
                """,
                (
                    int(family_id),
                    desired_app_version.strip(),
                    desired_model_version.strip(),
                    json.dumps(desired_rules, ensure_ascii=False),
                    timestamp if rules_patch else str(current_state.get("desired_rule_version") or ""),
                    json.dumps(desired_config, ensure_ascii=False),
                    timestamp if config_patch else str(current_state.get("desired_config_version") or ""),
                    timestamp,
                    str(device_id).strip(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (str(device_id).strip(),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device sync target was not persisted")
        return self._device_sync_state_to_dict(row)  # type: ignore[return-value]

    def set_device_sync_target(
        self,
        *,
        device_id: str,
        family_id: int,
        desired_app_version: str = "",
        desired_model_version: str = "",
        desired_rules: Optional[Dict[str, Any]] = None,
        desired_rule_version: Optional[str] = None,
        desired_config: Optional[Dict[str, Any]] = None,
        desired_config_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        current_state = self.ensure_device_sync_state(device_id, family_id)
        timestamp = now_iso()
        next_rules = dict(desired_rules if desired_rules is not None else (current_state.get("desired_rules") or self.get_rules()))
        next_config = dict(desired_config if desired_config is not None else (current_state.get("desired_config") or {}))
        next_rule_version = (
            str(current_state.get("desired_rule_version") or "")
            if desired_rules is None
            else (desired_rule_version if desired_rule_version is not None else timestamp)
        )
        next_config_version = (
            str(current_state.get("desired_config_version") or "")
            if desired_config is None
            else (desired_config_version if desired_config_version is not None else timestamp)
        )
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_sync_states
                SET
                    family_id = ?,
                    desired_app_version = ?,
                    desired_model_version = ?,
                    desired_rules_json = ?,
                    desired_rule_version = ?,
                    desired_config_json = ?,
                    desired_config_version = ?,
                    updated_at = ?
                WHERE device_id = ?
                """,
                (
                    int(family_id),
                    desired_app_version.strip(),
                    desired_model_version.strip(),
                    json.dumps(next_rules, ensure_ascii=False),
                    str(next_rule_version or ""),
                    json.dumps(next_config, ensure_ascii=False),
                    str(next_config_version or ""),
                    timestamp,
                    str(device_id).strip(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (str(device_id).strip(),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device sync target overwrite was not persisted")
        return self._device_sync_state_to_dict(row)  # type: ignore[return-value]

    def report_device_sync(
        self,
        *,
        device_id: str,
        family_id: int,
        app_version: str = "",
        model_version: str = "",
        applied_rule_version: str = "",
        status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current_state = self.ensure_device_sync_state(device_id, family_id)
        next_status = {
            **(current_state.get("reported_status") or {}),
            **(status or {}),
        }
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_sync_states
                SET
                    family_id = ?,
                    reported_app_version = ?,
                    reported_model_version = ?,
                    applied_rule_version = ?,
                    reported_status_json = ?,
                    last_seen_at = ?,
                    last_sync_at = ?,
                    updated_at = ?
                WHERE device_id = ?
                """,
                (
                    int(family_id),
                    app_version.strip(),
                    model_version.strip(),
                    applied_rule_version.strip(),
                    json.dumps(next_status, ensure_ascii=False),
                    timestamp,
                    timestamp,
                    timestamp,
                    str(device_id).strip(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (str(device_id).strip(),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device sync report was not persisted")
        return self._device_sync_state_to_dict(row)  # type: ignore[return-value]

    def mark_device_sync_rules_applied(self, device_id: str, applied_rule_version: str) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_sync_states
                SET applied_rule_version = ?, last_applied_at = ?, updated_at = ?
                WHERE device_id = ?
                """,
                (applied_rule_version.strip(), timestamp, timestamp, str(device_id).strip()),
            )
            row = conn.execute(
                "SELECT * FROM device_sync_states WHERE device_id = ? LIMIT 1",
                (str(device_id).strip(),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device sync apply state was not persisted")
        return self._device_sync_state_to_dict(row)  # type: ignore[return-value]

    def create_device_rollout(
        self,
        *,
        family_id: int,
        title: str,
        rollout_mode: str,
        status: str,
        target_app_version: str,
        target_model_version: str,
        rules_patch: Optional[Dict[str, Any]] = None,
        config_patch: Optional[Dict[str, Any]] = None,
        scope_device_ids: Optional[list[str]] = None,
        canary_device_ids: Optional[list[str]] = None,
        applied_device_ids: Optional[list[str]] = None,
        rolled_back_device_ids: Optional[list[str]] = None,
        previous_targets: Optional[Dict[str, Any]] = None,
        created_by_user_id: int = 0,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO device_rollouts (
                    family_id,
                    title,
                    rollout_mode,
                    status,
                    target_app_version,
                    target_model_version,
                    rules_patch_json,
                    config_patch_json,
                    scope_device_ids_json,
                    canary_device_ids_json,
                    applied_device_ids_json,
                    rolled_back_device_ids_json,
                    previous_targets_json,
                    created_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(family_id),
                    str(title or "").strip(),
                    str(rollout_mode or "canary").strip(),
                    str(status or "draft").strip(),
                    str(target_app_version or "").strip(),
                    str(target_model_version or "").strip(),
                    json.dumps(rules_patch or {}, ensure_ascii=False),
                    json.dumps(config_patch or {}, ensure_ascii=False),
                    json.dumps(scope_device_ids or [], ensure_ascii=False),
                    json.dumps(canary_device_ids or [], ensure_ascii=False),
                    json.dumps(applied_device_ids or [], ensure_ascii=False),
                    json.dumps(rolled_back_device_ids or [], ensure_ascii=False),
                    json.dumps(previous_targets or {}, ensure_ascii=False),
                    int(created_by_user_id),
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_rollouts WHERE id = ? LIMIT 1",
                (int(cursor.lastrowid),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device rollout was not persisted")
        return self._device_rollout_to_dict(row)  # type: ignore[return-value]

    def get_device_rollout(self, rollout_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM device_rollouts WHERE id = ? LIMIT 1",
                (int(rollout_id),),
            ).fetchone()
        return self._device_rollout_to_dict(row)

    def list_device_rollouts(self, family_id: int, limit: int = 20) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM device_rollouts
                WHERE family_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (int(family_id), max(1, min(int(limit), 100))),
            ).fetchall()
        return [self._device_rollout_to_dict(row) for row in rows if row is not None]

    def update_device_rollout_state(
        self,
        rollout_id: int,
        *,
        status: Optional[str] = None,
        canary_device_ids: Optional[list[str]] = None,
        applied_device_ids: Optional[list[str]] = None,
        rolled_back_device_ids: Optional[list[str]] = None,
        promoted_at: Optional[str] = None,
        rolled_back_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.get_device_rollout(rollout_id)
        if current is None:
            raise RuntimeError("Device rollout was not found")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE device_rollouts
                SET
                    status = ?,
                    canary_device_ids_json = ?,
                    applied_device_ids_json = ?,
                    rolled_back_device_ids_json = ?,
                    promoted_at = ?,
                    rolled_back_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(status or current.get("status") or "").strip(),
                    json.dumps(canary_device_ids if canary_device_ids is not None else (current.get("canary_device_ids") or []), ensure_ascii=False),
                    json.dumps(applied_device_ids if applied_device_ids is not None else (current.get("applied_device_ids") or []), ensure_ascii=False),
                    json.dumps(rolled_back_device_ids if rolled_back_device_ids is not None else (current.get("rolled_back_device_ids") or []), ensure_ascii=False),
                    promoted_at if promoted_at is not None else current.get("promoted_at"),
                    rolled_back_at if rolled_back_at is not None else current.get("rolled_back_at"),
                    timestamp,
                    int(rollout_id),
                ),
            )
            row = conn.execute(
                "SELECT * FROM device_rollouts WHERE id = ? LIMIT 1",
                (int(rollout_id),),
            ).fetchone()
        if row is None:
            raise RuntimeError("Device rollout state was not persisted")
        return self._device_rollout_to_dict(row)  # type: ignore[return-value]

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
            "activity_detection_enabled",
            "fire_detection_enabled",
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
            "fall_score_threshold",
            "fall_confirm_frames",
            "fall_confirm_seconds",
            "fall_recover_frames",
            "activity_detection_enabled",
            "fire_detection_enabled",
            "fire_event_score_threshold",
            "fire_motion_threshold",
            "fire_temporal_threshold",
            "fire_confirm_frames",
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
                    fall_score_threshold = ?,
                    fall_confirm_frames = ?,
                    fall_confirm_seconds = ?,
                    fall_recover_frames = ?,
                    activity_detection_enabled = ?,
                    fire_detection_enabled = ?,
                    fire_event_score_threshold = ?,
                    fire_motion_threshold = ?,
                    fire_temporal_threshold = ?,
                    fire_confirm_frames = ?,
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
                    float(next_values["fall_score_threshold"]),
                    int(next_values["fall_confirm_frames"]),
                    int(next_values["fall_confirm_seconds"]),
                    int(next_values["fall_recover_frames"]),
                    1 if next_values["activity_detection_enabled"] else 0,
                    1 if next_values["fire_detection_enabled"] else 0,
                    float(next_values["fire_event_score_threshold"]),
                    float(next_values["fire_motion_threshold"]),
                    float(next_values["fire_temporal_threshold"]),
                    int(next_values["fire_confirm_frames"]),
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
            main_message = "当前没有新的异常事件，视觉服务正在运行。"

        return {
            "date": today,
            "main_message": main_message,
            "events_count": events_count,
            "cameras_count": cameras_count,
            "online_cameras_count": online_count,
            "suggested_action": "查看视觉状态",
        }
