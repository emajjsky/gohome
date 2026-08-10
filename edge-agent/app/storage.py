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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # Runtime cleanup and event uploads can overlap during boot. Let the
        # short upload transaction wait for the bounded cleanup transaction.
        conn = sqlite3.connect(self.db_path, timeout=120)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 120000")
        conn.execute("PRAGMA foreign_keys = ON")
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
                    last_pet_seen_at TEXT,
                    last_pet_count INTEGER NOT NULL DEFAULT 0,
                    pet_types_json TEXT NOT NULL DEFAULT '[]',
                    deleted_at TEXT,
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
                    cloud_sync_status TEXT NOT NULL DEFAULT 'local_only',
                    cloud_synced_at TEXT,
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
                    claim_token TEXT NOT NULL DEFAULT '',
                    claimed_at TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(event_id) REFERENCES events(id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(camera_id) REFERENCES cameras(id)
                );

                CREATE TABLE IF NOT EXISTS media_lifecycle_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    snapshot_id INTEGER,
                    asset_id INTEGER,
                    provider TEXT NOT NULL DEFAULT 'localfs',
                    bucket TEXT NOT NULL DEFAULT 'local',
                    storage_path TEXT NOT NULL DEFAULT '',
                    object_key TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT,
                    claim_token TEXT NOT NULL DEFAULT '',
                    claimed_at TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(target_type, target_id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL,
                    FOREIGN KEY(asset_id) REFERENCES media_assets(id) ON DELETE SET NULL
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

                CREATE TABLE IF NOT EXISTS activity_export_cursors (
                    camera_id INTEGER PRIMARY KEY,
                    segment_started_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL,
                    person_count_max INTEGER NOT NULL DEFAULT 1,
                    postures_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id)
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
                    retention_class TEXT NOT NULL DEFAULT 'event_evidence',
                    retention_status TEXT NOT NULL DEFAULT 'active',
                    deletion_attempts INTEGER NOT NULL DEFAULT 0,
                    deletion_error TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    uploaded_at TEXT,
                    updated_at TEXT,
                    deleted_at TEXT,
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
                    no_person_seconds INTEGER NOT NULL,
                    offline_enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("DROP TABLE IF EXISTS app_push_tokens")
            conn.execute("DROP TABLE IF EXISTS notification_deliveries")
            conn.execute("DROP TABLE IF EXISTS video_service_nodes")
            self._ensure_column(conn, "snapshots", "retention_class", "TEXT NOT NULL DEFAULT 'routine'")
            self._ensure_column(conn, "snapshots", "retention_status", "TEXT NOT NULL DEFAULT 'active'")
            self._ensure_column(conn, "media_assets", "retention_class", "TEXT NOT NULL DEFAULT 'event_evidence'")
            self._ensure_column(conn, "media_assets", "retention_status", "TEXT NOT NULL DEFAULT 'active'")
            self._ensure_column(conn, "media_assets", "deletion_attempts", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "media_assets", "deletion_error", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "media_assets", "updated_at", "TEXT")
            self._ensure_column(conn, "media_assets", "deleted_at", "TEXT")
            conn.execute("UPDATE media_assets SET updated_at = COALESCE(updated_at, uploaded_at, created_at)")
            conn.execute(
                """
                UPDATE media_assets
                SET retention_class = 'package_artifact'
                WHERE id IN (SELECT asset_id FROM package_releases)
                """
            )
            self._migrate_media_lifecycle_foreign_keys(conn)
            self._ensure_column(conn, "snapshots", "person_count", "INTEGER")
            self._ensure_column(conn, "snapshots", "width", "INTEGER")
            self._ensure_column(conn, "snapshots", "height", "INTEGER")
            self._ensure_column(conn, "snapshots", "analysis_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "cameras", "last_pet_seen_at", "TEXT")
            self._ensure_column(conn, "cameras", "last_pet_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "cameras", "pet_types_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "cameras", "deleted_at", "TEXT")
            self._ensure_column(conn, "events", "detection_result_id", "INTEGER")
            self._ensure_column(conn, "events", "rule_evaluation_id", "INTEGER")
            self._ensure_column(conn, "events", "candidate_id", "INTEGER")
            self._ensure_column(conn, "events", "cloud_sync_status", "TEXT NOT NULL DEFAULT 'local_only'")
            self._ensure_column(conn, "events", "cloud_synced_at", "TEXT")
            upload_job_columns = self._table_columns(conn, "upload_jobs")
            requires_upload_lease_migration = "lease_expires_at" not in upload_job_columns
            self._ensure_column(conn, "upload_jobs", "claim_token", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "upload_jobs", "claimed_at", "TEXT")
            self._ensure_column(conn, "upload_jobs", "lease_expires_at", "TEXT")
            if requires_upload_lease_migration:
                self._migrate_legacy_upload_claims(conn)
            self._restore_archived_camera_references(conn)
            self._migrate_event_cloud_sync_status(conn)
            self._ensure_column(conn, "rules", "person_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fall_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "fall_score_threshold", "REAL NOT NULL DEFAULT 0.50")
            self._ensure_column(conn, "rules", "fall_confirm_frames", "INTEGER NOT NULL DEFAULT 2")
            self._ensure_column(conn, "rules", "fall_confirm_seconds", "INTEGER NOT NULL DEFAULT 4")
            self._ensure_column(conn, "rules", "fall_recover_frames", "INTEGER NOT NULL DEFAULT 2")
            self._ensure_column(conn, "rules", "activity_detection_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "rules", "no_person_seconds", "INTEGER NOT NULL DEFAULT 300")
            self._ensure_column(conn, "rules", "motion_threshold", "REAL NOT NULL DEFAULT 0.015")
            self._ensure_column(conn, "rules", "black_brightness_threshold", "REAL NOT NULL DEFAULT 18")
            self._ensure_column(conn, "rules", "black_contrast_threshold", "REAL NOT NULL DEFAULT 4")
            self._ensure_column(conn, "rules", "yolo_confidence", "REAL NOT NULL DEFAULT 0.20")
            self._drop_obsolete_rules_columns(conn)
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
                        no_person_seconds,
                        offline_enabled,
                        updated_at
                    )
                    VALUES (1, 5, 0.015, 18, 4, 0.20, 300, 1, 1, 1, 1, 0.50, 2, 4, 2, 1, 300, 1, ?)
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
                CREATE INDEX IF NOT EXISTS idx_media_lifecycle_jobs_status
                    ON media_lifecycle_jobs(status, next_attempt_at, id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_retention
                    ON snapshots(retention_status, captured_at, id);
                CREATE INDEX IF NOT EXISTS idx_media_assets_retention
                    ON media_assets(retention_status, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_presence_sessions_camera_status
                    ON presence_sessions(camera_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_posture_episodes_camera_status
                    ON posture_episodes(camera_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_posture_episodes_track_status
                    ON posture_episodes(camera_id, track_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_activity_export_cursors_updated_at
                    ON activity_export_cursors(updated_at, camera_id);
                """
            )

    def _lifecycle_retry_at(self, attempt_count: int) -> str:
        delay = min(3600, max(30, 30 * (2 ** max(0, min(int(attempt_count), 7) - 1))))
        return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()

    def _enqueue_media_lifecycle_job(
        self,
        conn: sqlite3.Connection,
        *,
        target_type: str,
        target_id: int,
        snapshot_id: int | None = None,
        asset_id: int | None = None,
        provider: str = "localfs",
        bucket: str = "local",
        storage_path: str = "",
        object_key: str = "",
        reason: str = "retention",
    ) -> bool:
        timestamp = now_iso()
        cursor = conn.execute(
            """
            INSERT INTO media_lifecycle_jobs (
                target_type, target_id, snapshot_id, asset_id, provider, bucket,
                storage_path, object_key, reason, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(target_type, target_id) DO NOTHING
            """,
            (
                str(target_type), int(target_id),
                int(snapshot_id) if snapshot_id else None,
                int(asset_id) if asset_id else None,
                str(provider or "localfs"), str(bucket or "local"),
                str(storage_path or "").strip().lstrip("/"),
                str(object_key or "").strip().lstrip("/"),
                str(reason or "retention"), timestamp, timestamp,
            ),
        )
        return bool(cursor.rowcount)

    def process_media_lifecycle_jobs(
        self,
        *,
        snapshot_dir: Path,
        object_storage_dir: Path | None = None,
        limit: int = 32,
    ) -> Dict[str, Any]:
        """Delete managed bytes first, then commit their database cleanup.

        SQLite's write transaction stays open while local bytes are removed.
        That prevents a concurrent event/upload transaction from acquiring a
        snapshot reference after the safety check and before row deletion.
        Remote providers are intentionally left retryable until a provider
        adapter is supplied; silently deleting their database rows would leak
        cloud objects.
        """
        snapshot_root = Path(snapshot_dir).resolve()
        object_root = Path(object_storage_dir or snapshot_root.parent / "object_storage").resolve()
        processed = completed = failed = blocked = 0
        completed_by_type: Dict[str, int] = {}
        errors: list[Dict[str, Any]] = []
        for _ in range(max(1, min(int(limit), 100))):
            job = None
            try:
                with self.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    timestamp = now_iso()
                    row = conn.execute(
                        """
                        SELECT * FROM media_lifecycle_jobs
                        WHERE (
                            status IN ('pending', 'failed')
                            AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                        ) OR (
                            status = 'deleting'
                            AND lease_expires_at IS NOT NULL
                            AND lease_expires_at <= ?
                        )
                        ORDER BY created_at ASC, id ASC
                        LIMIT 1
                        """,
                        (timestamp, timestamp),
                    ).fetchone()
                    if row is None:
                        conn.rollback()
                        break
                    job = dict(row)
                    attempt = int(job.get("attempt_count") or 0) + 1
                    lease = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
                    conn.execute(
                        """
                        UPDATE media_lifecycle_jobs
                        SET status = 'deleting', attempt_count = ?, claim_token = ?,
                            claimed_at = ?, lease_expires_at = ?, last_error = '', updated_at = ?
                        WHERE id = ?
                        """,
                        (attempt, f"lifecycle:{secrets.token_urlsafe(12)}", timestamp, lease, timestamp, int(job["id"])),
                    )
                    provider = str(job.get("provider") or "localfs").lower()
                    if provider not in {"localfs", "local", "signed-localfs"}:
                        error = f"provider_not_supported_on_edge:{provider}"
                        conn.execute(
                            """
                            UPDATE media_lifecycle_jobs
                            SET status = 'failed', last_error = ?, next_attempt_at = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (error, self._lifecycle_retry_at(attempt), timestamp, int(job["id"])),
                        )
                        if str(job.get("target_type") or "") == "asset":
                            conn.execute(
                                """
                                UPDATE media_assets
                                SET deletion_attempts = ?, deletion_error = ?, updated_at = ?
                                WHERE id = ?
                                """,
                                (attempt, error, timestamp, int(job["target_id"])),
                            )
                        conn.commit()
                        processed += 1
                        failed += 1
                        errors.append({"job_id": int(job["id"]), "error": error})
                        continue

                    target_type = str(job.get("target_type") or "")
                    if target_type == "snapshot":
                        root = snapshot_root
                        relative = str(job.get("storage_path") or "").lstrip("/")
                        candidate = (root / relative).resolve()
                    else:
                        root = object_root
                        relative = str(job.get("object_key") or "").lstrip("/")
                        candidate = (root / relative).resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        raise ValueError("managed media path escapes storage root")

                    target_id = int(job["target_id"])
                    if target_type == "snapshot":
                        refs = conn.execute(
                            """
                            SELECT 1 FROM events WHERE snapshot_id = ?
                            UNION ALL SELECT 1 FROM detection_results WHERE snapshot_id = ?
                            UNION ALL SELECT 1 FROM rule_evaluations WHERE snapshot_id = ?
                            UNION ALL SELECT 1 FROM observation_logs WHERE last_snapshot_id = ?
                            UNION ALL SELECT 1 FROM presence_sessions
                                WHERE representative_snapshot_id = ? AND status = 'open'
                            UNION ALL SELECT 1 FROM posture_episodes
                                WHERE representative_snapshot_id = ? AND status = 'open'
                            UNION ALL SELECT 1 FROM upload_jobs
                                WHERE snapshot_id = ? AND status != 'completed'
                            UNION ALL SELECT 1 FROM media_assets
                                WHERE snapshot_id = ? AND retention_status != 'deleted'
                            LIMIT 1
                            """,
                            (target_id,) * 8,
                        ).fetchone()
                        if refs is not None:
                            conn.execute(
                                "UPDATE snapshots SET retention_status = 'active' WHERE id = ?",
                                (target_id,),
                            )
                            conn.execute(
                                """
                                UPDATE media_lifecycle_jobs
                                SET status = 'cancelled', last_error = 'snapshot_became_protected',
                                    next_attempt_at = NULL, claim_token = '', lease_expires_at = NULL,
                                    completed_at = ?, updated_at = ?
                                WHERE id = ?
                                """,
                                (timestamp, timestamp, int(job["id"])),
                            )
                            conn.commit()
                            processed += 1
                            blocked += 1
                            continue

                    if candidate.exists():
                        if not candidate.is_file():
                            raise ValueError("managed media path is not a file")
                        candidate.unlink()

                    if target_type == "snapshot":
                        conn.execute("DELETE FROM snapshots WHERE id = ? AND retention_status = 'deleting'", (target_id,))
                    elif target_type == "asset":
                        conn.execute(
                            """
                            UPDATE media_assets
                            SET status = 'deleted', retention_status = 'deleted', deleted_at = ?,
                                deletion_attempts = ?, deletion_error = '', updated_at = ?
                            WHERE id = ? AND retention_status = 'deleting'
                            """,
                            (timestamp, attempt, timestamp, target_id),
                        )
                    elif target_type == "upload_session":
                        conn.execute("DELETE FROM media_upload_sessions WHERE id = ?", (target_id,))
                    else:
                        raise ValueError(f"unsupported_lifecycle_target:{target_type}")

                    conn.execute(
                        """
                        UPDATE media_lifecycle_jobs
                        SET status = 'completed', last_error = '', next_attempt_at = NULL,
                            claim_token = '', lease_expires_at = NULL, completed_at = ?, updated_at = ?,
                            snapshot_id = CASE WHEN target_type = 'snapshot' THEN NULL ELSE snapshot_id END
                        WHERE id = ?
                        """,
                        (timestamp, timestamp, int(job["id"])),
                    )
                    conn.commit()
                    completed += 1
                    processed += 1
                    completed_by_type[target_type] = completed_by_type.get(target_type, 0) + 1
            except Exception as exc:
                failed += 1
                processed += 1
                error = str(exc)[:1000]
                if job is not None:
                    try:
                        with self.connect() as conn:
                            timestamp = now_iso()
                            conn.execute(
                                """
                                UPDATE media_lifecycle_jobs
                                SET status = 'failed', last_error = ?, next_attempt_at = ?,
                                    claim_token = '', lease_expires_at = NULL, updated_at = ?
                                WHERE id = ?
                                """,
                                (error, self._lifecycle_retry_at(int(job.get("attempt_count") or 1)), timestamp, int(job["id"])),
                            )
                            if str(job.get("target_type") or "") == "asset":
                                conn.execute(
                                    """
                                    UPDATE media_assets
                                    SET deletion_attempts = deletion_attempts + 1,
                                        deletion_error = ?, updated_at = ?
                                    WHERE id = ?
                                    """,
                                    (error, timestamp, int(job["target_id"])),
                                )
                    except Exception as persist_error:
                        error = f"{error}; lifecycle_state_persist_failed:{persist_error}"
                errors.append({"job_id": int(job["id"]) if job else None, "error": error})
        return {
            "processed": processed,
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "completed_by_type": completed_by_type,
            "errors": errors,
        }

    def prune_runtime_history(
        self,
        *,
        snapshot_dir: Path,
        object_storage_dir: Path | None = None,
        retention_hours: int = 24,
        completed_upload_retention_days: int = 7,
        event_evidence_retention_hours: int = 24,
        local_event_retention_days: int = 30,
        batch_size: int = 5000,
        discard_live_preview_uploads: bool = True,
        force_oldest: bool = False,
    ) -> Dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(retention_hours)))).isoformat()
        event_evidence_cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=max(1, int(event_evidence_retention_hours)))
        ).isoformat()
        event_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(local_event_retention_days)))
        ).isoformat()
        upload_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(completed_upload_retention_days)))
        ).isoformat()
        limit = max(100, min(int(batch_size), 20000))
        deleted: Dict[str, int] = {}

        with self.connect() as conn:
            # Once the complete event and all of its evidence are accepted by
            # the cloud, local heavyweight inference rows become a cache. Keep
            # a short replay window, then detach them so normal age pruning can
            # recycle the oldest pages without risking unsent evidence.
            synced_event_rows = conn.execute(
                """
                SELECT id
                FROM events
                WHERE cloud_sync_status = 'completed'
                  AND cloud_synced_at IS NOT NULL
                  AND cloud_synced_at < ?
                  AND occurred_at < ?
                  AND (
                      snapshot_id IS NOT NULL
                      OR detection_result_id IS NOT NULL
                      OR rule_evaluation_id IS NOT NULL
                      OR candidate_id IS NOT NULL
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM upload_jobs pending
                      WHERE pending.event_id = events.id
                        AND pending.status != 'completed'
                  )
                ORDER BY occurred_at, id
                LIMIT ?
                """,
                (event_evidence_cutoff, event_evidence_cutoff, limit),
            ).fetchall()
            synced_event_ids = [int(row["id"]) for row in synced_event_rows]
            if synced_event_ids:
                placeholders = ",".join("?" for _ in synced_event_ids)
                deleted["event_runtime_links"] = conn.execute(
                    f"""
                    UPDATE events
                    SET snapshot_id = NULL,
                        detection_result_id = NULL,
                        rule_evaluation_id = NULL,
                        candidate_id = NULL
                    WHERE id IN ({placeholders})
                    """,
                    synced_event_ids,
                ).rowcount
            else:
                deleted["event_runtime_links"] = 0

            expired_event_rows = conn.execute(
                """
                SELECT id
                FROM events
                WHERE occurred_at < ?
                  AND (
                      (cloud_sync_status = 'completed' AND cloud_synced_at IS NOT NULL)
                      OR cloud_sync_status = 'local_only'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM upload_jobs pending
                      WHERE pending.event_id = events.id
                        AND pending.status != 'completed'
                  )
                ORDER BY occurred_at, id
                LIMIT ?
                """,
                (event_cutoff, limit),
            ).fetchall()
            expired_event_ids = [int(row["id"]) for row in expired_event_rows]
            if expired_event_ids:
                placeholders = ",".join("?" for _ in expired_event_ids)
                conn.execute(
                    f"UPDATE event_candidates SET promoted_event_id = NULL WHERE promoted_event_id IN ({placeholders})",
                    expired_event_ids,
                )
                conn.execute(
                    f"UPDATE media_assets SET event_id = NULL WHERE event_id IN ({placeholders})",
                    expired_event_ids,
                )
                deleted["event_ingests"] = conn.execute(
                    f"DELETE FROM event_ingests WHERE event_id IN ({placeholders})",
                    expired_event_ids,
                ).rowcount
                deleted["expired_event_upload_jobs"] = conn.execute(
                    f"DELETE FROM upload_jobs WHERE event_id IN ({placeholders}) AND status = 'completed'",
                    expired_event_ids,
                ).rowcount
                deleted["events"] = conn.execute(
                    f"DELETE FROM events WHERE id IN ({placeholders})",
                    expired_event_ids,
                ).rowcount
            else:
                deleted["event_ingests"] = 0
                deleted["expired_event_upload_jobs"] = 0
                deleted["events"] = 0

            deleted["live_preview_upload_jobs"] = 0
            if discard_live_preview_uploads:
                deleted["live_preview_upload_jobs"] = conn.execute(
                    """
                    DELETE FROM upload_jobs
                    WHERE id IN (
                        SELECT id FROM upload_jobs
                        WHERE object_type = 'live_frame'
                          AND status != 'uploading'
                        ORDER BY id
                        LIMIT ?
                    )
                    """,
                    (limit,),
                ).rowcount

            deleted["observation_logs"] = conn.execute(
                """
                DELETE FROM observation_logs
                WHERE id IN (
                    SELECT id FROM observation_logs
                    WHERE status = 'closed' AND updated_at < ?
                    ORDER BY id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

            deleted["presence_sessions"] = conn.execute(
                """
                DELETE FROM presence_sessions
                WHERE id IN (
                    SELECT id FROM presence_sessions
                    WHERE status = 'closed' AND updated_at < ?
                    ORDER BY id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

            deleted["posture_episodes"] = conn.execute(
                """
                DELETE FROM posture_episodes
                WHERE id IN (
                    SELECT id FROM posture_episodes
                    WHERE status = 'closed' AND updated_at < ?
                    ORDER BY id
                    LIMIT ?
                )
                """,
                (cutoff, limit),
            ).rowcount

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

            expired_session_rows = conn.execute(
                """
                SELECT id, provider, bucket, object_key
                FROM media_upload_sessions
                WHERE status != 'completed' AND expires_at < ?
                ORDER BY expires_at, id
                LIMIT ?
                """,
                (now_iso(), limit),
            ).fetchall()
            deleted["media_upload_sessions_planned"] = 0
            for row in expired_session_rows:
                if self._enqueue_media_lifecycle_job(
                    conn,
                    target_type="upload_session",
                    target_id=int(row["id"]),
                    provider=str(row["provider"] or "signed-localfs"),
                    bucket=str(row["bucket"] or "local"),
                    object_key=str(row["object_key"] or ""),
                    reason="expired_upload_session",
                ):
                    deleted["media_upload_sessions_planned"] += 1

            asset_age_cutoff = now_iso() if force_oldest else upload_cutoff
            asset_rows = conn.execute(
                """
                SELECT ma.id, ma.provider, ma.bucket, ma.object_key
                FROM media_assets ma
                LEFT JOIN events e ON e.id = ma.event_id
                WHERE ma.retention_status = 'active'
                  AND ma.retention_class IN ('routine_cache', 'event_evidence', 'verification_evidence')
                  AND COALESCE(ma.uploaded_at, ma.created_at) < ?
                  AND LOWER(COALESCE(ma.metadata_json, '{}')) NOT LIKE '%family_memory%'
                  AND NOT EXISTS (
                      SELECT 1 FROM package_releases pr WHERE pr.asset_id = ma.id
                  )
                  AND (
                      ma.event_id IS NULL
                      OR (
                          e.cloud_sync_status = 'completed'
                          AND e.cloud_synced_at IS NOT NULL
                          AND e.cloud_synced_at < ?
                      )
                  )
                ORDER BY COALESCE(ma.uploaded_at, ma.created_at), ma.id
                LIMIT ?
                """,
                (asset_age_cutoff, event_evidence_cutoff, limit),
            ).fetchall()
            deleted["media_assets_planned"] = 0
            for row in asset_rows:
                asset_id = int(row["id"])
                if self._enqueue_media_lifecycle_job(
                    conn,
                    target_type="asset",
                    target_id=asset_id,
                    asset_id=asset_id,
                    provider=str(row["provider"] or "localfs"),
                    bucket=str(row["bucket"] or "local"),
                    object_key=str(row["object_key"] or ""),
                    reason="expired_media_asset",
                ):
                    conn.execute(
                        "UPDATE media_assets SET retention_status = 'deleting' WHERE id = ?",
                        (asset_id,),
                    )
                    deleted["media_assets_planned"] += 1

            snapshot_rows = conn.execute(
                """
                SELECT s.id, s.image_path
                FROM snapshots s
                WHERE s.retention_status = 'active'
                  AND (s.captured_at < ? OR ? = 1)
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
                      SELECT snapshot_id FROM media_assets
                      WHERE snapshot_id IS NOT NULL AND retention_status != 'deleted'
                  )
                  AND s.id NOT IN (
                      SELECT MAX(latest.id) FROM snapshots latest GROUP BY latest.camera_id
                  )
                ORDER BY s.id
                LIMIT ?
                """,
                (cutoff, 1 if force_oldest else 0, limit),
            ).fetchall()
            snapshot_ids = [int(row["id"]) for row in snapshot_rows]
            if snapshot_ids:
                placeholders = ",".join("?" for _ in snapshot_ids)
                # Closed runtime summaries and completed jobs remain useful
                # after their short-lived local preview image expires.
                conn.execute(
                    f"""
                    UPDATE presence_sessions
                    SET representative_snapshot_id = NULL
                    WHERE status != 'open'
                      AND representative_snapshot_id IN ({placeholders})
                    """,
                    snapshot_ids,
                )
                conn.execute(
                    f"""
                    UPDATE posture_episodes
                    SET representative_snapshot_id = NULL
                    WHERE status != 'open'
                      AND representative_snapshot_id IN ({placeholders})
                    """,
                    snapshot_ids,
                )
                conn.execute(
                    f"""
                    UPDATE upload_jobs
                    SET snapshot_id = NULL
                    WHERE status = 'completed'
                      AND snapshot_id IN ({placeholders})
                    """,
                    snapshot_ids,
                )
                planned = 0
                for row in snapshot_rows:
                    snapshot_id = int(row["id"])
                    if self._enqueue_media_lifecycle_job(
                        conn,
                        target_type="snapshot",
                        target_id=snapshot_id,
                        snapshot_id=snapshot_id,
                        storage_path=str(row["image_path"] or ""),
                        reason="critical_watermark" if force_oldest else "retention_expired",
                    ):
                        planned += 1
                if planned:
                    conn.execute(
                        f"UPDATE snapshots SET retention_status = 'deleting' WHERE id IN ({placeholders})",
                        snapshot_ids,
                    )
                deleted["snapshots_planned"] = planned
            else:
                deleted["snapshots_planned"] = 0

        lifecycle = self.process_media_lifecycle_jobs(
            snapshot_dir=snapshot_dir,
            object_storage_dir=object_storage_dir,
            limit=min(limit, 100),
        )
        deleted["snapshots"] = int(lifecycle.get("completed_by_type", {}).get("snapshot", 0))
        deleted["media_assets"] = int(lifecycle.get("completed_by_type", {}).get("asset", 0))
        deleted["media_upload_sessions"] = int(
            lifecycle.get("completed_by_type", {}).get("upload_session", 0)
        )
        pending_lifecycle = 0
        due_lifecycle = 0
        with self.connect() as conn:
            pending_lifecycle = int(conn.execute(
                "SELECT COUNT(*) FROM media_lifecycle_jobs WHERE status NOT IN ('completed', 'cancelled')"
            ).fetchone()[0])
            timestamp = now_iso()
            due_lifecycle = int(conn.execute(
                """
                SELECT COUNT(*) FROM media_lifecycle_jobs
                WHERE status = 'pending'
                   OR (status = 'failed' AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
                   OR (status = 'deleting' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
                """,
                (timestamp, timestamp),
            ).fetchone()[0])

        return {
            "cutoff": cutoff,
            "event_evidence_cutoff": event_evidence_cutoff,
            "event_cutoff": event_cutoff,
            "deleted": deleted,
            "deleted_snapshot_files": deleted["snapshots"],
            "skipped_snapshot_files": int(lifecycle.get("failed", 0)) + int(lifecycle.get("blocked", 0)),
            "media_lifecycle": lifecycle,
            "pending_media_lifecycle_jobs": pending_lifecycle,
            "due_media_lifecycle_jobs": due_lifecycle,
            "has_more": due_lifecycle > 0 or any(count >= limit for count in deleted.values()),
        }

    @staticmethod
    def _directory_bytes(root: Path) -> int:
        total = 0
        if not root.exists():
            return total
        for candidate in root.rglob("*"):
            try:
                if candidate.is_file():
                    total += candidate.stat().st_size
            except OSError:
                continue
        return total

    def runtime_storage_status(
        self,
        snapshot_dir: Path,
        *,
        object_storage_dir: Path | None = None,
        runtime_dir: Path | None = None,
        retention_hours: int = 24,
    ) -> Dict[str, Any]:
        disk = shutil.disk_usage(self.db_path.parent)
        used_percent = (float(disk.used) / float(disk.total) * 100.0) if disk.total else 0.0
        database_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        wal_path = Path(f"{self.db_path}-wal")
        shm_path = Path(f"{self.db_path}-shm")
        database_sidecar_bytes = sum(
            path.stat().st_size for path in (wal_path, shm_path) if path.exists()
        )
        snapshot_root = Path(snapshot_dir)
        object_root = Path(object_storage_dir or snapshot_root.parent / "object_storage")
        runtime_root = Path(runtime_dir or snapshot_root.parent / "runtime")
        snapshot_bytes = self._directory_bytes(snapshot_root)
        object_storage_bytes = self._directory_bytes(object_root)
        runtime_bytes = self._directory_bytes(runtime_root)
        freelist_bytes = 0
        try:
            with self.connect() as conn:
                page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
                freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
                freelist_bytes = page_size * freelist_count
        except sqlite3.Error:
            freelist_bytes = 0
        return {
            "database_bytes": database_bytes,
            "database_sidecar_bytes": database_sidecar_bytes,
            "database_reusable_bytes": freelist_bytes,
            "snapshot_bytes": snapshot_bytes,
            "object_storage_bytes": object_storage_bytes,
            "runtime_files_bytes": runtime_bytes,
            "runtime_allocated_bytes": (
                database_bytes + database_sidecar_bytes + snapshot_bytes
                + object_storage_bytes + runtime_bytes
            ),
            "runtime_live_bytes": (
                max(0, database_bytes - freelist_bytes) + database_sidecar_bytes
                + snapshot_bytes + object_storage_bytes + runtime_bytes
            ),
            "disk_total_bytes": disk.total,
            "disk_used_bytes": disk.used,
            "disk_free_bytes": disk.free,
            "disk_used_percent": round(used_percent, 2),
            "retention_hours": max(1, int(retention_hours)),
            "snapshot_dir": str(snapshot_root),
            "object_storage_dir": str(object_root),
            "runtime_dir": str(runtime_root),
        }

    def compact_runtime_database(
        self,
        *,
        snapshot_dir: Path,
        object_storage_dir: Path | None = None,
        runtime_dir: Path | None = None,
        minimum_reusable_bytes: int = 64 * 1024 * 1024,
    ) -> Dict[str, Any]:
        before = self.runtime_storage_status(
            snapshot_dir,
            object_storage_dir=object_storage_dir,
            runtime_dir=runtime_dir,
        )
        reusable = int(before.get("database_reusable_bytes") or 0)
        database_bytes = int(before.get("database_bytes") or 0)
        if reusable < max(4 * 1024 * 1024, int(minimum_reusable_bytes)):
            return {"compacted": False, "reason": "reusable_pages_below_threshold", "before": before}
        required_free = database_bytes + 128 * 1024 * 1024
        if int(before.get("disk_free_bytes") or 0) < required_free:
            return {"compacted": False, "reason": "insufficient_temporary_space", "before": before}

        conn = sqlite3.connect(self.db_path, timeout=120)
        try:
            conn.execute("PRAGMA busy_timeout = 120000")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
        finally:
            conn.close()
        after = self.runtime_storage_status(
            snapshot_dir,
            object_storage_dir=object_storage_dir,
            runtime_dir=runtime_dir,
        )
        return {
            "compacted": True,
            "reclaimed_bytes": max(0, database_bytes - int(after.get("database_bytes") or 0)),
            "before": before,
            "after": after,
        }

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        if column not in self._table_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _drop_obsolete_rules_columns(self, conn: sqlite3.Connection) -> None:
        obsolete_columns = (
            "fire_detection_enabled",
            "fire_event_score_threshold",
            "fire_motion_threshold",
            "fire_temporal_threshold",
            "fire_confirm_frames",
        )
        columns = self._table_columns(conn, "rules")
        for column in obsolete_columns:
            if column in columns:
                conn.execute(f"ALTER TABLE rules DROP COLUMN {column}")
                columns.remove(column)

    def _migrate_media_lifecycle_foreign_keys(self, conn: sqlite3.Connection) -> None:
        foreign_keys = {
            str(row["from"]): str(row["on_delete"]).upper()
            for row in conn.execute("PRAGMA foreign_key_list(media_lifecycle_jobs)").fetchall()
        }
        if foreign_keys.get("snapshot_id") == "SET NULL" and foreign_keys.get("asset_id") == "SET NULL":
            return

        conn.execute("DROP TABLE IF EXISTS media_lifecycle_jobs_v2")
        conn.execute(
            """
            CREATE TABLE media_lifecycle_jobs_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                snapshot_id INTEGER,
                asset_id INTEGER,
                provider TEXT NOT NULL DEFAULT 'localfs',
                bucket TEXT NOT NULL DEFAULT 'local',
                storage_path TEXT NOT NULL DEFAULT '',
                object_key TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                next_attempt_at TEXT,
                claim_token TEXT NOT NULL DEFAULT '',
                claimed_at TEXT,
                lease_expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                UNIQUE(target_type, target_id),
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL,
                FOREIGN KEY(asset_id) REFERENCES media_assets(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO media_lifecycle_jobs_v2 (
                id, target_type, target_id, snapshot_id, asset_id, provider, bucket,
                storage_path, object_key, reason, status, attempt_count, last_error,
                next_attempt_at, claim_token, claimed_at, lease_expires_at,
                created_at, updated_at, completed_at
            )
            SELECT
                id,
                target_type,
                target_id,
                CASE
                    WHEN snapshot_id IS NULL OR EXISTS (
                        SELECT 1 FROM snapshots WHERE snapshots.id = media_lifecycle_jobs.snapshot_id
                    ) THEN snapshot_id
                    ELSE NULL
                END,
                CASE
                    WHEN asset_id IS NULL OR EXISTS (
                        SELECT 1 FROM media_assets WHERE media_assets.id = media_lifecycle_jobs.asset_id
                    ) THEN asset_id
                    ELSE NULL
                END,
                provider,
                bucket,
                storage_path,
                object_key,
                reason,
                status,
                attempt_count,
                last_error,
                next_attempt_at,
                claim_token,
                claimed_at,
                lease_expires_at,
                created_at,
                updated_at,
                completed_at
            FROM media_lifecycle_jobs
            ORDER BY id
            """
        )
        conn.execute("DROP TABLE media_lifecycle_jobs")
        conn.execute("ALTER TABLE media_lifecycle_jobs_v2 RENAME TO media_lifecycle_jobs")

    def _migrate_event_cloud_sync_status(self, conn: sqlite3.Connection) -> None:
        # This classification is intentionally one-shot. Re-running it at every
        # boot would turn newly-created local events into pending uploads.
        conn.execute(
            """
            UPDATE events
            SET
                cloud_sync_status = CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM upload_jobs unfinished
                        WHERE unfinished.event_id = events.id
                          AND unfinished.status != 'completed'
                    ) THEN 'pending'
                    WHEN EXISTS (
                        SELECT 1
                        FROM upload_jobs uploaded
                        WHERE uploaded.event_id = events.id
                          AND uploaded.job_type = 'event_upload'
                          AND uploaded.status = 'completed'
                    ) THEN 'completed'
                    ELSE 'local_only'
                END,
                cloud_synced_at = CASE
                    WHEN NOT EXISTS (
                        SELECT 1
                        FROM upload_jobs unfinished
                        WHERE unfinished.event_id = events.id
                          AND unfinished.status != 'completed'
                    ) AND EXISTS (
                        SELECT 1
                        FROM upload_jobs uploaded
                        WHERE uploaded.event_id = events.id
                          AND uploaded.job_type = 'event_upload'
                          AND uploaded.status = 'completed'
                    ) THEN (
                        SELECT MAX(COALESCE(completed_at, updated_at, created_at))
                        FROM upload_jobs uploaded
                        WHERE uploaded.event_id = events.id
                          AND uploaded.job_type = 'event_upload'
                          AND uploaded.status = 'completed'
                    )
                    ELSE NULL
                END
            """
        )

    def _restore_archived_camera_references(self, conn: sqlite3.Connection) -> None:
        referenced_rows = conn.execute(
            """
            SELECT camera_id FROM snapshots WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM detection_results WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM rule_evaluations WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM event_candidates WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM events WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM upload_jobs WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM observation_logs WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM presence_sessions WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM posture_episodes WHERE camera_id IS NOT NULL
            UNION SELECT camera_id FROM activity_export_cursors WHERE camera_id IS NOT NULL
            """
        ).fetchall()
        existing_ids = {
            int(row["id"])
            for row in conn.execute("SELECT id FROM cameras").fetchall()
        }
        timestamp = now_iso()
        for row in referenced_rows:
            camera_id = int(row["camera_id"])
            if camera_id in existing_ids:
                continue
            event = conn.execute(
                """
                SELECT room, MIN(occurred_at) AS first_seen_at, MAX(occurred_at) AS last_seen_at
                FROM events
                WHERE camera_id = ?
                """,
                (camera_id,),
            ).fetchone()
            created_at = str(event["first_seen_at"] or timestamp) if event else timestamp
            updated_at = str(event["last_seen_at"] or created_at) if event else created_at
            room = str(event["room"] or "") if event else ""
            conn.execute(
                """
                INSERT INTO cameras (
                    id, name, room, stream_url, username, password, enabled, status,
                    last_seen_at, last_error, last_pet_seen_at, last_pet_count,
                    pet_types_json, deleted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 'deleted', NULL, '', NULL, 0, '[]', ?, ?, ?)
                """,
                (
                    camera_id,
                    f"历史摄像头 #{camera_id}",
                    room,
                    f"archived:{camera_id}",
                    timestamp,
                    created_at,
                    updated_at,
                ),
            )
            existing_ids.add(camera_id)

    def _migrate_legacy_upload_claims(self, conn: sqlite3.Connection) -> None:
        # Older workers could leave a row in uploading forever after a process
        # restart because they had no claim lease. Make those rows retryable
        # exactly once when lease columns are introduced.
        timestamp = now_iso()
        conn.execute(
            """
            UPDATE upload_jobs
            SET
                status = 'failed',
                last_error = CASE
                    WHEN TRIM(COALESCE(last_error, '')) = ''
                        THEN 'legacy_upload_claim_recovered'
                    ELSE SUBSTR(last_error || '; legacy_upload_claim_recovered', 1, 1000)
                END,
                next_attempt_at = ?,
                claim_token = '',
                claimed_at = NULL,
                lease_expires_at = NULL,
                updated_at = ?
            WHERE status = 'uploading'
            """,
            (timestamp, timestamp),
        )

    def _refresh_event_cloud_sync_status(
        self,
        conn: sqlite3.Connection,
        event_id: int,
        *,
        synced_at: Optional[str] = None,
    ) -> None:
        unfinished = conn.execute(
            """
            SELECT 1
            FROM upload_jobs
            WHERE event_id = ? AND status != 'completed'
            LIMIT 1
            """,
            (int(event_id),),
        ).fetchone()
        if unfinished is not None:
            conn.execute(
                "UPDATE events SET cloud_sync_status = 'pending', cloud_synced_at = NULL WHERE id = ?",
                (int(event_id),),
            )
            return
        completed_event_upload = conn.execute(
            """
            SELECT COALESCE(completed_at, updated_at, created_at) AS synced_at
            FROM upload_jobs
            WHERE event_id = ? AND job_type = 'event_upload' AND status = 'completed'
            ORDER BY COALESCE(completed_at, updated_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (int(event_id),),
        ).fetchone()
        if completed_event_upload is None:
            conn.execute(
                "UPDATE events SET cloud_sync_status = 'local_only', cloud_synced_at = NULL WHERE id = ?",
                (int(event_id),),
            )
            return
        conn.execute(
            """
            UPDATE events
            SET cloud_sync_status = 'completed', cloud_synced_at = ?
            WHERE id = ?
            """,
            (synced_at or str(completed_event_upload["synced_at"] or now_iso()), int(event_id)),
        )

    def _camera_to_dict(self, row: sqlite3.Row, include_secret: bool = False) -> Dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        data["pet_types"] = json.loads(data.pop("pet_types_json", "[]") or "[]")
        if not include_secret:
            data.pop("password", None)
        return data

    def _device_sync_state_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["desired_rules"] = json.loads(data.pop("desired_rules_json", "{}") or "{}")
        data["desired_config"] = json.loads(data.pop("desired_config_json", "{}") or "{}")
        data["reported_status"] = json.loads(data.pop("reported_status_json", "{}") or "{}")
        return data

    def _media_asset_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
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

    def _device_binding_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data

    def _device_token_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["heartbeat"] = json.loads(data.pop("last_heartbeat_json", "{}") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        data.pop("token_hash", None)
        return data

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
    def list_cameras(self, include_secret: bool = False) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cameras WHERE deleted_at IS NULL ORDER BY id DESC"
            ).fetchall()
        return [self._camera_to_dict(row, include_secret=include_secret) for row in rows]

    def get_camera(self, camera_id: int, include_secret: bool = False) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM cameras WHERE id = ? AND deleted_at IS NULL",
                (camera_id,),
            ).fetchone()
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
                WHERE id = ? AND deleted_at IS NULL
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
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE cameras
                SET stream_url = ?, username = NULL, password = NULL, enabled = 0,
                    status = 'deleted', last_error = '', last_pet_seen_at = NULL,
                    last_pet_count = 0, pet_types_json = '[]', deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (f"archived:{int(camera_id)}", timestamp, timestamp, int(camera_id)),
            )
        return cursor.rowcount > 0

    def update_camera_status(self, camera_id: int, status: str, last_error: str = "") -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            if status == "online":
                conn.execute(
                    """
                    UPDATE cameras
                    SET status = ?, last_seen_at = ?, last_error = NULL, updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (status, timestamp, timestamp, camera_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE cameras
                    SET status = ?, last_error = ?, updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
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
        pets = analysis.get("pets") if isinstance(analysis.get("pets"), list) else []
        objects = [
            {
                "category": "person",
                "confidence": person.get("confidence"),
                "bbox": person.get("bbox"),
                "fall_candidate": bool(person.get("fall_candidate")),
            }
            for person in people
        ] + [
            {
                "category": pet.get("type") or pet.get("label") or "pet",
                "label_zh": pet.get("label_zh"),
                "confidence": pet.get("confidence"),
                "bbox": pet.get("bbox"),
                "scene_zone_label": pet.get("scene_zone_label"),
                "scene_zone_label_zh": pet.get("scene_zone_label_zh"),
                "person_evidence_eligible": False,
                "fall_evidence_eligible": False,
            }
            for pet in pets
        ]
        quality_flags = list(analysis.get("tags") or [])
        raw_confidence_summary = {
            "person_confidences": [person.get("confidence") for person in people if person.get("confidence") is not None],
            "pet_confidences": [pet.get("confidence") for pet in pets if pet.get("confidence") is not None],
            "motion_score": analysis.get("motion_score"),
            "brightness": analysis.get("brightness"),
            "contrast": analysis.get("contrast"),
        }
        detector_backend = str(analysis.get("detector_backend") or "basic")
        model_name = analysis.get("model_name")
        if detector_backend == "yolo" and not model_name:
            model_name = analysis.get("yolo_model")
        persisted_analysis_keys = (
            "pipeline_version",
            "model_version",
            "detector_backend",
            "model_name",
            "image_width",
            "image_height",
            "brightness",
            "contrast",
            "black_screen",
            "motion_score",
            "motion_detected",
            "person_count",
            "pet_count",
            "pose_count",
            "fall_candidate",
            "fall_score",
            "pose_fall_candidate",
            "pose_fall_score",
            "meal_candidate",
            "stillness_candidate",
            "daze_candidate",
            "tags",
        )
        persisted_analysis = {
            key: analysis.get(key)
            for key in persisted_analysis_keys
            if key in analysis
        }
        persisted_analysis["schema_version"] = "gohome-detection-summary-v1"
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
                    json.dumps(persisted_analysis, ensure_ascii=False),
                    created_at,
                ),
            )
            detection_result_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM detection_results WHERE id = ?", (detection_result_id,)).fetchone()
        if row is None:
            raise RuntimeError("DetectionResult was not persisted")
        return self._detection_result_to_dict(row)

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

    def aggregate_event_candidate_into_recent_event(
        self,
        *,
        candidate_id: int,
        camera_id: Optional[int],
        event_type: str,
        seconds: int,
    ) -> Optional[Dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, int(seconds)))).isoformat()
        timestamp = now_iso()
        event_id: Optional[int] = None
        with self.connect() as conn:
            event_row = conn.execute(
                """
                SELECT id, payload
                FROM events
                WHERE camera_id IS ? AND type = ? AND occurred_at >= ?
                ORDER BY occurred_at DESC, id DESC
                LIMIT 1
                """,
                (camera_id, str(event_type or ""), cutoff),
            ).fetchone()
            candidate_row = conn.execute(
                "SELECT * FROM event_candidates WHERE id = ? LIMIT 1",
                (int(candidate_id),),
            ).fetchone()
            if event_row is None or candidate_row is None:
                return None

            event_id = int(event_row["id"])
            payload = json.loads(event_row["payload"] or "{}")
            aggregation = (
                payload.get("candidate_aggregation")
                if isinstance(payload.get("candidate_aggregation"), dict)
                else {}
            )
            occurrences = (
                list(aggregation.get("occurrences") or [])
                if isinstance(aggregation.get("occurrences"), list)
                else []
            )
            if not any(int(item.get("candidate_id") or 0) == int(candidate_id) for item in occurrences if isinstance(item, dict)):
                snapshot_ids = json.loads(candidate_row["evidence_snapshot_ids_json"] or "[]")
                occurrences.append({
                    "candidate_id": int(candidate_id),
                    "observed_at": str(candidate_row["started_at"] or timestamp),
                    "snapshot_ids": [int(item) for item in snapshot_ids if item],
                    "rule_evaluation_id": candidate_row["rule_evaluation_id"],
                    "summary": str(candidate_row["summary"] or ""),
                })
            payload["candidate_aggregation"] = {
                "schema_version": "gohome-event-candidate-aggregation-v1",
                "repeat_count": len(occurrences),
                "total_candidate_count": len(occurrences) + 1,
                "last_observed_at": str(candidate_row["started_at"] or timestamp),
                "occurrences": occurrences[-24:],
            }
            conn.execute(
                "UPDATE events SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), event_id),
            )
            upload_rows = conn.execute(
                """
                SELECT id, payload_json
                FROM upload_jobs
                WHERE event_id = ? AND job_type = 'event_upload' AND status IN ('pending', 'failed')
                """,
                (event_id,),
            ).fetchall()
            for upload_row in upload_rows:
                upload_payload = json.loads(upload_row["payload_json"] or "{}")
                upload_payload["payload"] = payload
                conn.execute(
                    "UPDATE upload_jobs SET payload_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(upload_payload, ensure_ascii=False), timestamp, int(upload_row["id"])),
                )
            conn.execute(
                """
                UPDATE event_candidates
                SET status = 'aggregated', promoted_event_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (event_id, timestamp, int(candidate_id)),
            )
        return self.get_event(event_id) if event_id is not None else None

    def list_event_candidates(self, limit: int = 20, status: Optional[str] = None) -> list[Dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status == "active":
            where = """
                WHERE ec.status NOT IN ('suppressed', 'aggregated')
                  AND ec.event_type NOT IN ('no_motion', 'no_person')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM events resolved_event
                    WHERE resolved_event.id = ec.promoted_event_id
                      AND json_extract(resolved_event.payload, '$.resolution') = 'false_positive'
                  )
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
            activity_jobs = self._close_activity_export_cursor(
                conn,
                camera_id=int(camera_id),
                reason=str(reason or "camera_stopped"),
                timestamp=timestamp,
            )
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
            "activity_intervals_enqueued": len(activity_jobs),
        }

    def reconcile_camera_runtime_state(self, *, close_stale_open: bool = False) -> Dict[str, int]:
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
            stale_observation_count = 0
            stale_presence_count = 0
            stale_posture_count = 0
            stale_activity_count = 0
            if close_stale_open:
                activity_camera_ids = [
                    int(row["camera_id"])
                    for row in conn.execute("SELECT camera_id FROM activity_export_cursors").fetchall()
                ]
                stale_activity_count = sum(
                    len(self._close_activity_export_cursor(
                        conn,
                        camera_id=camera_id,
                        reason="worker_restart",
                        timestamp=timestamp,
                    ))
                    for camera_id in activity_camera_ids
                )
                stale_observation_cursor = conn.execute(
                    """
                    UPDATE observation_logs
                    SET status = 'closed', ended_at = ?,
                        duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                        updated_at = ?
                    WHERE status = 'open'
                    """,
                    (timestamp, timestamp, timestamp),
                )
                stale_presence_cursor = conn.execute(
                    """
                    UPDATE presence_sessions
                    SET status = 'closed', ended_at = ?,
                        duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                        close_reason = 'worker_restart', updated_at = ?
                    WHERE status = 'open'
                    """,
                    (timestamp, timestamp, timestamp),
                )
                stale_posture_cursor = conn.execute(
                    """
                    UPDATE posture_episodes
                    SET status = 'closed', ended_at = ?,
                        duration_seconds = MAX(0, CAST(strftime('%s', ?) - strftime('%s', started_at) AS INTEGER)),
                        close_reason = 'worker_restart', updated_at = ?
                    WHERE status = 'open'
                    """,
                    (timestamp, timestamp, timestamp),
                )
                stale_observation_count = int(stale_observation_cursor.rowcount or 0)
                stale_presence_count = int(stale_presence_cursor.rowcount or 0)
                stale_posture_count = int(stale_posture_cursor.rowcount or 0)
        return {
            "orphan_observation_logs_closed": int(observation_cursor.rowcount or 0),
            "orphan_presence_sessions_closed": int(presence_cursor.rowcount or 0),
            "orphan_posture_episodes_closed": int(posture_cursor.rowcount or 0),
            "stale_observation_logs_closed": stale_observation_count,
            "stale_presence_sessions_closed": stale_presence_count,
            "stale_posture_episodes_closed": stale_posture_count,
            "stale_activity_intervals_enqueued": stale_activity_count,
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
        captured_at = now_iso()
        analysis_data = analysis or {}
        pet_count = max(0, int(analysis_data.get("pet_count") or 0))
        pet_types = sorted({str(item) for item in (analysis_data.get("pet_types") or []) if str(item)})
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
                    captured_at,
                    width,
                    height,
                    brightness,
                    motion_score,
                    person_count,
                    json.dumps(list(tags)),
                    json.dumps(analysis_data, ensure_ascii=False),
                ),
            )
            if pet_count > 0:
                conn.execute(
                    """
                    UPDATE cameras
                    SET last_pet_seen_at = ?, last_pet_count = ?, pet_types_json = ?, updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (captured_at, pet_count, json.dumps(pet_types, ensure_ascii=False), captured_at, int(camera_id)),
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

    def camera_presence_status(
        self,
        camera_id: int,
        *,
        window_minutes: int = 60,
        expected_interval_seconds: int = 5,
    ) -> Dict[str, Any]:
        window_seconds = max(60, int(window_minutes) * 60)
        expected_samples = max(1, window_seconds // max(1, int(expected_interval_seconds)))
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(captured_at) AS last_observed_at,
                       COUNT(*) AS observed_samples,
                       SUM(CASE WHEN person_count > 0 THEN 1 ELSE 0 END) AS person_samples
                FROM snapshots
                WHERE camera_id = ? AND julianday(captured_at) >= julianday('now', ?)
                """,
                (int(camera_id), f"-{window_seconds} seconds"),
            ).fetchone()
            historical = conn.execute(
                """
                SELECT MAX(last_seen_at) AS last_person_seen_at
                FROM presence_sessions
                WHERE camera_id = ?
                """,
                (int(camera_id),),
            ).fetchone()
            snapshot_historical = conn.execute(
                "SELECT MAX(captured_at) AS last_person_seen_at FROM snapshots WHERE camera_id = ? AND person_count > 0",
                (int(camera_id),),
            ).fetchone()
            camera = conn.execute(
                "SELECT last_pet_seen_at, last_pet_count, pet_types_json FROM cameras WHERE id = ?",
                (int(camera_id),),
            ).fetchone()
        observed_samples = int(row["observed_samples"] or 0)
        return {
            "last_observed_at": row["last_observed_at"],
            "last_person_seen_at": max(
                filter(None, [historical["last_person_seen_at"], snapshot_historical["last_person_seen_at"]]),
                default=None,
            ),
            "observation_window_minutes": max(1, int(window_minutes)),
            "observed_samples": observed_samples,
            "person_samples": int(row["person_samples"] or 0),
            "last_pet_seen_at": camera["last_pet_seen_at"] if camera else None,
            "last_pet_count": int((camera["last_pet_count"] if camera else 0) or 0),
            "pet_types": json.loads((camera["pet_types_json"] if camera else "[]") or "[]"),
            "expected_samples": expected_samples,
            "observation_coverage": round(min(1.0, observed_samples / expected_samples), 4),
        }

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

    def advance_activity_export(
        self,
        *,
        camera_id: int,
        room: str,
        observed_at: str,
        visible: bool,
        person_count: int,
        postures: Iterable[str],
        confidence: Optional[float],
        flush: bool,
        reason: str,
        max_gap_seconds: float,
    ) -> list[Dict[str, Any]]:
        observed = self._parse_iso_datetime(observed_at)
        clean_postures = sorted({str(item or "").strip() for item in postures if str(item or "").strip()})
        bounded_confidence = None if confidence is None else max(0.0, min(1.0, float(confidence)))
        timestamp = now_iso()
        jobs: list[Dict[str, Any]] = []
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM activity_export_cursors WHERE camera_id = ?",
                (int(camera_id),),
            ).fetchone()
            if cursor is not None:
                started = self._parse_iso_datetime(str(cursor["segment_started_at"]))
                last_observed = self._parse_iso_datetime(str(cursor["last_observed_at"]))
                stale = (observed - last_observed).total_seconds() > max(60.0, float(max_gap_seconds))
                previous_postures = json.loads(cursor["postures_json"] or "[]")
                signature_changed = clean_postures != sorted(str(item) for item in previous_postures)
                if not visible or flush or stale or signature_changed:
                    ended = last_observed if stale else observed
                    if ended > started:
                        jobs.extend(self._enqueue_activity_interval_chunks(
                            conn,
                            camera_id=int(camera_id),
                            room=str(room or ""),
                            started_at=started,
                            ended_at=ended,
                            person_count=max(int(cursor["person_count_max"] or 1), 1),
                            postures=previous_postures,
                            confidence=cursor["confidence"],
                            reason="observation_gap" if stale else str(reason or "activity_update"),
                            timestamp=timestamp,
                        ))

            if visible:
                reset = cursor is None or bool(flush) or (
                    cursor is not None
                    and (
                        (observed - self._parse_iso_datetime(str(cursor["last_observed_at"]))).total_seconds()
                        > max(60.0, float(max_gap_seconds))
                        or clean_postures != sorted(str(item) for item in json.loads(cursor["postures_json"] or "[]"))
                    )
                )
                if reset:
                    conn.execute(
                        """
                        INSERT INTO activity_export_cursors (
                            camera_id, segment_started_at, last_observed_at, person_count_max,
                            postures_json, confidence, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(camera_id) DO UPDATE SET
                            segment_started_at = excluded.segment_started_at,
                            last_observed_at = excluded.last_observed_at,
                            person_count_max = excluded.person_count_max,
                            postures_json = excluded.postures_json,
                            confidence = excluded.confidence,
                            updated_at = excluded.updated_at
                        """,
                        (
                            int(camera_id), observed.isoformat(), observed.isoformat(),
                            max(1, int(person_count)), json.dumps(clean_postures, ensure_ascii=False),
                            bounded_confidence, timestamp, timestamp,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE activity_export_cursors
                        SET last_observed_at = ?,
                            person_count_max = MAX(person_count_max, ?),
                            confidence = CASE
                                WHEN confidence IS NULL THEN ?
                                WHEN ? IS NULL THEN confidence
                                ELSE (confidence + ?) / 2.0
                            END,
                            updated_at = ?
                        WHERE camera_id = ?
                        """,
                        (
                            observed.isoformat(), max(1, int(person_count)), bounded_confidence,
                            bounded_confidence, bounded_confidence, timestamp, int(camera_id),
                        ),
                    )
            else:
                conn.execute("DELETE FROM activity_export_cursors WHERE camera_id = ?", (int(camera_id),))
        return jobs

    def _enqueue_activity_interval_chunks(
        self,
        conn: sqlite3.Connection,
        *,
        camera_id: int,
        room: str,
        started_at: datetime,
        ended_at: datetime,
        person_count: int,
        postures: Iterable[str],
        confidence: Optional[float],
        reason: str,
        timestamp: str,
    ) -> list[Dict[str, Any]]:
        jobs: list[Dict[str, Any]] = []
        chunk_start = started_at
        max_chunk = timedelta(hours=6)
        while chunk_start < ended_at:
            chunk_end = min(ended_at, chunk_start + max_chunk)
            source_hash = hashlib.sha256(
                f"{camera_id}|{chunk_start.isoformat()}|{chunk_end.isoformat()}".encode("utf-8")
            ).hexdigest()[:24]
            source_interval_id = f"camera-{camera_id}-{source_hash}"
            idempotency_key = f"activity-interval:{source_interval_id}"
            payload = {
                "schema_version": "gohome-activity-interval-v1",
                "source_interval_id": source_interval_id,
                "local_camera_id": int(camera_id),
                "room": str(room or ""),
                "started_at": chunk_start.isoformat(),
                "ended_at": chunk_end.isoformat(),
                "person_count_max": max(1, int(person_count)),
                "postures": sorted({str(item or "").strip() for item in postures if str(item or "").strip()}),
                "confidence": None if confidence is None else round(max(0.0, min(1.0, float(confidence))), 4),
                "metadata": {
                    "source": "edge_presence_timeline",
                    "close_reason": str(reason or "activity_update"),
                    "contains_media": False,
                },
            }
            insert_cursor = conn.execute(
                """
                INSERT OR IGNORE INTO upload_jobs (
                    job_type, object_type, status, priority, idempotency_key,
                    family_id, device_id, event_id, snapshot_id, camera_id,
                    payload_json, attempt_count, last_error, next_attempt_at,
                    created_at, updated_at, completed_at
                ) VALUES (
                    'activity_interval_upload', 'activity_interval', 'pending', 70, ?,
                    NULL, '', NULL, NULL, ?, ?, 0, '', NULL, ?, ?, NULL
                )
                """,
                (idempotency_key, int(camera_id), json.dumps(payload, ensure_ascii=False), timestamp, timestamp),
            )
            if int(insert_cursor.rowcount or 0) > 0:
                row = conn.execute(
                    "SELECT * FROM upload_jobs WHERE idempotency_key = ? LIMIT 1",
                    (idempotency_key,),
                ).fetchone()
                job = self._upload_job_to_dict(row)
                if job is not None:
                    jobs.append(job)
            chunk_start = chunk_end
        return jobs

    def _close_activity_export_cursor(
        self,
        conn: sqlite3.Connection,
        *,
        camera_id: int,
        reason: str,
        timestamp: str,
    ) -> list[Dict[str, Any]]:
        cursor = conn.execute(
            """
            SELECT aec.*, c.room AS camera_room
            FROM activity_export_cursors aec
            LEFT JOIN cameras c ON c.id = aec.camera_id
            WHERE aec.camera_id = ?
            """,
            (int(camera_id),),
        ).fetchone()
        if cursor is None:
            return []
        started = self._parse_iso_datetime(str(cursor["segment_started_at"]))
        ended = self._parse_iso_datetime(str(cursor["last_observed_at"]))
        jobs = []
        if ended > started:
            jobs = self._enqueue_activity_interval_chunks(
                conn,
                camera_id=int(camera_id),
                room=str(cursor["camera_room"] or ""),
                started_at=started,
                ended_at=ended,
                person_count=max(1, int(cursor["person_count_max"] or 1)),
                postures=json.loads(cursor["postures_json"] or "[]"),
                confidence=cursor["confidence"],
                reason=str(reason or "camera_stopped"),
                timestamp=timestamp,
            )
        conn.execute("DELETE FROM activity_export_cursors WHERE camera_id = ?", (int(camera_id),))
        return jobs

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

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
        cloud_sync_status: str = "local_only",
    ) -> Dict[str, Any]:
        event_occurred_at = str(occurred_at or "").strip() or now_iso()
        normalized_sync_status = str(cloud_sync_status or "local_only").strip()
        if normalized_sync_status not in {"local_only", "pending", "completed"}:
            raise ValueError("Unsupported event cloud sync status")
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    camera_id, detection_result_id, rule_evaluation_id, candidate_id,
                    type, room, summary, level, snapshot_id, occurred_at, payload,
                    cloud_sync_status, cloud_synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
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
                    normalized_sync_status,
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
        next_attempt_at: Optional[str] = None,
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
                    VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?, ?, NULL)
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
                        str(next_attempt_at or "").strip() or None,
                        timestamp,
                        timestamp,
                    ),
                )
                job_id = int(cursor.lastrowid)
                if event_id:
                    conn.execute(
                        """
                        UPDATE events
                        SET cloud_sync_status = 'pending', cloud_synced_at = NULL
                        WHERE id = ?
                        """,
                        (int(event_id),),
                    )
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

    def enqueue_event_evidence_finalize(
        self,
        event: Dict[str, Any],
        *,
        settle_seconds: float = 0.8,
        max_wait_seconds: float = 2.5,
    ) -> Dict[str, Any]:
        from datetime import datetime, timedelta, timezone

        event_id = int(event["id"])
        occurred_at = str(event.get("occurred_at") or now_iso())
        try:
            occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            occurred = datetime.now(timezone.utc)
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        settle = max(0.3, min(float(settle_seconds), 2.0))
        max_wait = max(settle, min(float(max_wait_seconds), 5.0))
        return self.enqueue_upload_job(
            job_type="event_evidence_finalize",
            object_type="event_evidence",
            idempotency_key=f"event-evidence-finalize:{event_id}",
            priority=3,
            event_id=event_id,
            snapshot_id=int(event["snapshot_id"]) if event.get("snapshot_id") else None,
            camera_id=int(event["camera_id"]) if event.get("camera_id") else None,
            next_attempt_at=(occurred + timedelta(seconds=settle)).isoformat(),
            payload={
                "schema_version": "gohome-event-evidence-finalize-v1",
                "event_id": event_id,
                "settle_seconds": settle,
                "max_wait_seconds": max_wait,
                "occurred_at": occurred_at,
            },
        )

    def finalize_event_evidence(
        self,
        event_id: int,
        *,
        settle_seconds: float = 0.8,
        max_wait_seconds: float = 2.5,
    ) -> Dict[str, Any]:
        from datetime import datetime, timedelta, timezone

        event = self.get_event(int(event_id))
        if event is None:
            raise ValueError("event evidence finalization target was not found")
        payload = dict(event.get("payload") or {})
        existing_finalization = payload.get("evidence_finalization")
        if isinstance(existing_finalization, dict) and existing_finalization.get("finalized"):
            return event
        if event.get("type") != "fall_candidate" or not event.get("camera_id"):
            payload["evidence_finalization"] = {
                "schema_version": "gohome-event-evidence-finalize-v1",
                "finalized": True,
                "reason": "settled_frame_not_required",
                "finalized_at": now_iso(),
            }
            with self.connect() as conn:
                conn.execute(
                    "UPDATE events SET payload = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), int(event_id)),
                )
            return self.get_event(int(event_id)) or event

        occurred_text = str(event.get("occurred_at") or now_iso())
        try:
            occurred = datetime.fromisoformat(occurred_text.replace("Z", "+00:00"))
        except ValueError:
            occurred = datetime.now(timezone.utc)
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        settle = max(0.3, min(float(settle_seconds), 2.0))
        max_wait = max(settle, min(float(max_wait_seconds), 5.0))
        target_at = (occurred + timedelta(seconds=settle)).isoformat()
        deadline_at = (occurred + timedelta(seconds=max_wait)).isoformat()

        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        original_bundle = evidence.get("temporal_evidence_bundle") if isinstance(evidence, dict) else {}
        if not isinstance(original_bundle, dict) or not original_bundle:
            original_bundle = payload.get("temporal_evidence_bundle") if isinstance(payload.get("temporal_evidence_bundle"), dict) else {}
        track_id = str(original_bundle.get("track_id") or "")
        selected_snapshot: Optional[Dict[str, Any]] = None
        selected_track: Optional[Dict[str, Any]] = None
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM snapshots
                WHERE camera_id = ? AND captured_at >= ? AND captured_at <= ?
                ORDER BY captured_at ASC, id ASC
                """,
                (int(event["camera_id"]), target_at, deadline_at),
            ).fetchall()
        for row in rows:
            snapshot = self._snapshot_to_dict(row)
            analysis = snapshot.get("analysis") if isinstance(snapshot.get("analysis"), dict) else {}
            graph = analysis.get("pose_factor_graph") if isinstance(analysis.get("pose_factor_graph"), dict) else {}
            tracks = graph.get("tracks") if isinstance(graph.get("tracks"), list) else []
            matching = next(
                (
                    item for item in tracks
                    if isinstance(item, dict)
                    and track_id
                    and str(item.get("track_id") or "") == track_id
                    and str(item.get("posture") or "") == "lying"
                ),
                None,
            )
            if matching is None:
                continue
            selected_snapshot = snapshot
            selected_track = matching
            break

        original_snapshots = original_bundle.get("snapshots") if isinstance(original_bundle.get("snapshots"), list) else []
        stable_roles = [
            dict(item)
            for item in original_snapshots
            if isinstance(item, dict) and str(item.get("role") or "") in {"before", "transition", "evidence"}
        ][:3]
        if selected_snapshot is not None and selected_track is not None:
            stable_roles.append({
                "snapshot_id": int(selected_snapshot["id"]),
                "snapshot_path": str(selected_snapshot.get("image_path") or ""),
                "observed_at": str(selected_snapshot.get("captured_at") or ""),
                "postures": [str(selected_track.get("posture") or "lying")],
                "motion_score": selected_snapshot.get("motion_score"),
                "role": "current",
            })
            finalized_bundle = {
                **original_bundle,
                "schema_version": "temporal-evidence-bundle-v1",
                "selection_policy": "role-aware-post-settle-v4",
                "window_ended_at": str(selected_snapshot.get("captured_at") or ""),
                "snapshots": stable_roles,
            }
            evidence = {**evidence, "temporal_evidence_bundle": finalized_bundle}
            payload["evidence"] = evidence
            payload["temporal_evidence_bundle"] = finalized_bundle
            snapshot_id = int(selected_snapshot["id"])
            reason = "same_track_settled_lying"
        else:
            snapshot_id = int(event["snapshot_id"]) if event.get("snapshot_id") else None
            reason = "settled_same_track_frame_unavailable"
        payload["evidence_finalization"] = {
            "schema_version": "gohome-event-evidence-finalize-v1",
            "finalized": True,
            "reason": reason,
            "track_id": track_id,
            "target_at": target_at,
            "deadline_at": deadline_at,
            "selected_snapshot_id": snapshot_id,
            "finalized_at": now_iso(),
        }
        with self.connect() as conn:
            conn.execute(
                "UPDATE events SET snapshot_id = ?, payload = ? WHERE id = ?",
                (snapshot_id, json.dumps(payload, ensure_ascii=False), int(event_id)),
            )
        return self.get_event(int(event_id)) or event

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
        evidence = base_payload["payload"].get("evidence") if isinstance(base_payload["payload"], dict) else {}
        temporal_bundle = evidence.get("temporal_evidence_bundle") if isinstance(evidence, dict) else {}
        temporal_snapshots = temporal_bundle.get("snapshots") if isinstance(temporal_bundle, dict) else []
        if not isinstance(temporal_snapshots, list):
            temporal_snapshots = []
        current_evidence = next(
            (
                item for item in temporal_snapshots
                if isinstance(item, dict) and int(item.get("snapshot_id") or 0) == int(snapshot_id or 0)
            ),
            {},
        )
        evidence_selection_policy = str(temporal_bundle.get("selection_policy") or "")
        # Persist all evidence jobs before making the event job visible to the
        # uploader thread. Otherwise it can claim the event between commits and
        # submit an evidence-free incident even though evidence is being queued.
        jobs: list[Dict[str, Any]] = []
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
                        "evidence_frame_role": "current",
                        "captured_at": str(current_evidence.get("observed_at") or event.get("occurred_at") or ""),
                        "evidence_selection_policy": evidence_selection_policy,
                        "postures": (
                            current_evidence.get("postures")
                            if isinstance(current_evidence.get("postures"), list)
                            else []
                        ),
                    },
                )
            )
        unique_frames: list[Dict[str, Any]] = []
        seen_snapshot_ids = {snapshot_id} if snapshot_id else set()
        for item in temporal_snapshots if isinstance(temporal_snapshots, list) else []:
            if not isinstance(item, dict):
                continue
            frame_snapshot_id = item.get("snapshot_id")
            frame_snapshot_path = str(item.get("snapshot_path") or "").strip().lstrip("/")
            if not frame_snapshot_id or not frame_snapshot_path or int(frame_snapshot_id) in seen_snapshot_ids:
                continue
            seen_snapshot_ids.add(int(frame_snapshot_id))
            unique_frames.append({
                "snapshot_id": int(frame_snapshot_id),
                "snapshot_path": frame_snapshot_path,
                "observed_at": str(item.get("observed_at") or ""),
                "postures": item.get("postures") if isinstance(item.get("postures"), list) else [],
                "role": str(item.get("role") or ""),
            })
        for index, frame in enumerate(unique_frames[:3]):
            role = frame["role"] if frame["role"] in {"before", "transition", "evidence"} else (
                ("before", "transition", "evidence")[index]
            )
            jobs.append(
                self.enqueue_upload_job(
                    job_type="media_upload",
                    object_type="event_keyframe",
                    idempotency_key=f"snapshot:{frame['snapshot_id']}:event:{event_id}:keyframe",
                    priority=4,
                    event_id=event_id,
                    snapshot_id=int(frame["snapshot_id"]),
                    camera_id=camera_id,
                    payload={
                        **base_payload,
                        "snapshot_id": int(frame["snapshot_id"]),
                        "snapshot_path": frame["snapshot_path"],
                        "captured_at": frame["observed_at"],
                        "target": "object_storage",
                        "content_type": "image/jpeg",
                        "purpose": f"{evidence_purpose}_keyframe",
                        "evidence_frame_role": role,
                        "evidence_selection_policy": evidence_selection_policy,
                        "postures": frame["postures"],
                    },
                )
            )
        jobs.append(
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

    def claim_next_upload_job(
        self,
        *,
        lease_seconds: int = 120,
        worker_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=max(30, int(lease_seconds)))
        ).isoformat()
        claim_token = f"{str(worker_id or 'upload-worker').strip()}:{secrets.token_urlsafe(18)}"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT *
                FROM upload_jobs
                WHERE (
                        status IN ('pending', 'failed')
                        AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                      )
                   OR (
                        status = 'uploading'
                        AND lease_expires_at IS NOT NULL
                        AND lease_expires_at <= ?
                      )
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (timestamp, timestamp),
            ).fetchone()
            if row is None:
                return None
            job_id = int(row["id"])
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'uploading',
                    attempt_count = attempt_count + 1,
                    last_error = CASE
                        WHEN status = 'uploading' THEN 'upload_lease_expired; reclaimed'
                        ELSE ''
                    END,
                    claim_token = ?,
                    claimed_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (claim_token, timestamp, lease_expires_at, timestamp, job_id),
            )
            claimed = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
        return self._upload_job_to_dict(claimed)

    def complete_upload_job(
        self,
        job_id: int,
        result: Dict[str, Any],
        *,
        claim_token: str = "",
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
            job = self._upload_job_to_dict(row)
            if job is None:
                return None
            expected_token = str(claim_token or "").strip()
            if expected_token and (
                str(job.get("status") or "") != "uploading"
                or str(job.get("claim_token") or "") != expected_token
            ):
                return None
            payload = dict(job.get("payload") or {})
            payload["upload_result"] = result
            cursor = conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'completed',
                    payload_json = ?,
                    last_error = '',
                    next_attempt_at = NULL,
                    claim_token = '',
                    lease_expires_at = NULL,
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                  AND (? = '' OR (status = 'uploading' AND claim_token = ?))
                """,
                (
                    json.dumps(payload, ensure_ascii=False),
                    timestamp,
                    timestamp,
                    int(job_id),
                    expected_token,
                    expected_token,
                ),
            )
            if cursor.rowcount != 1:
                return None
            if job.get("event_id"):
                self._refresh_event_cloud_sync_status(
                    conn,
                    int(job["event_id"]),
                    synced_at=timestamp if str(job.get("job_type") or "") == "event_upload" else None,
                )
            updated = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
        return self._upload_job_to_dict(updated)

    def fail_upload_job(
        self,
        job_id: int,
        error: str,
        *,
        retry_after_seconds: int = 60,
        claim_token: str = "",
    ) -> Optional[Dict[str, Any]]:
        from datetime import datetime, timedelta, timezone

        timestamp = now_iso()
        next_attempt_at = (datetime.now(timezone.utc) + timedelta(seconds=max(5, int(retry_after_seconds)))).isoformat()
        expected_token = str(claim_token or "").strip()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE upload_jobs
                SET status = 'failed',
                    last_error = ?,
                    next_attempt_at = ?,
                    claim_token = '',
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE id = ?
                  AND (? = '' OR (status = 'uploading' AND claim_token = ?))
                """,
                (
                    str(error or "")[:1000],
                    next_attempt_at,
                    timestamp,
                    int(job_id),
                    expected_token,
                    expected_token,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
        return self._upload_job_to_dict(row)

    def upload_jobs_for_event(
        self,
        *,
        event_id: int,
        job_type: str,
    ) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM upload_jobs
                WHERE event_id = ? AND job_type = ?
                ORDER BY priority ASC, created_at ASC, id ASC
                """,
                (int(event_id), str(job_type or "").strip()),
            ).fetchall()
        return [job for row in rows if (job := self._upload_job_to_dict(row)) is not None]

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
                    c.status AS camera_status,
                    c.last_seen_at AS camera_last_seen_at,
                    c.last_error AS camera_last_error,
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
                    c.status AS camera_status,
                    c.last_seen_at AS camera_last_seen_at,
                    c.last_error AS camera_last_error,
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

    def latest_unresolved_event(
        self,
        *,
        camera_id: int,
        event_types: list[str],
        track_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        clean_types = [str(item or "").strip() for item in event_types if str(item or "").strip()]
        if not clean_types:
            return None
        clean_track_id = str(track_id or "").strip()
        placeholders = ",".join("?" for _ in clean_types)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT e.*, c.name AS camera_name, s.image_path AS snapshot_path,
                       ec.status AS candidate_status
                FROM events e
                LEFT JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN snapshots s ON s.id = e.snapshot_id
                LEFT JOIN event_candidates ec ON ec.id = e.candidate_id
                WHERE e.camera_id = ?
                  AND e.type IN ({placeholders})
                  AND e.acknowledged = 0
                  AND COALESCE(json_extract(e.payload, '$.resolution'), '') = ''
                  AND (
                    ? = ''
                    OR json_extract(e.payload, '$.evaluation.state.fall_target.track_id') = ?
                    OR json_extract(e.payload, '$.rule.observed.track_id') = ?
                    OR json_extract(e.payload, '$.temporal_evidence_bundle.track_id') = ?
                    OR json_extract(e.payload, '$.evidence.temporal_evidence_bundle.track_id') = ?
                    OR json_extract(e.payload, '$.pose_factor_graph.fast_fall_track.track_id') = ?
                    OR json_extract(e.payload, '$.evidence.pose_factor_graph.fast_fall_track.track_id') = ?
                  )
                ORDER BY e.occurred_at DESC, e.id DESC
                LIMIT 1
                """,
                (int(camera_id), *clean_types, *([clean_track_id] * 7)),
            ).fetchone()
        return self._event_to_dict(row) if row else None

    def resolve_event_from_edge(
        self,
        event_id: int,
        *,
        resolution: str,
        resolved_at: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_event(int(event_id))
        if current is None:
            return None
        payload = current.get("payload") or {}
        if payload.get("resolution"):
            return current
        payload["resolution"] = str(resolution or "").strip()
        payload["resolved_at"] = str(resolved_at or now_iso())
        payload["recovery_evidence"] = evidence or {}
        with self.connect() as conn:
            conn.execute(
                "UPDATE events SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), int(event_id)),
            )
        return self.get_event(int(event_id))

    def enqueue_event_state_upload(
        self,
        event: Dict[str, Any],
        *,
        state: str,
        resolution: str,
        observed_at: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event_id = int(event["id"])
        return self.enqueue_upload_job(
            job_type="event_state_upload",
            object_type="event_state",
            idempotency_key=f"event-state:{event_id}:{state}:{resolution}",
            priority=8,
            event_id=event_id,
            camera_id=int(event["camera_id"]) if event.get("camera_id") else None,
            payload={
                "schema_version": "gohome-event-state-v1",
                "event_id": event_id,
                "event_type": event.get("type"),
                "camera_id": event.get("camera_id"),
                "state": str(state or ""),
                "resolution": str(resolution or ""),
                "observed_at": str(observed_at or now_iso()),
                "evidence": evidence or {},
            },
        )

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
            "offline_enabled",
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
            "no_person_seconds",
            "offline_enabled",
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
                    no_person_seconds = ?,
                    offline_enabled = ?,
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
                    int(next_values["no_person_seconds"]),
                    1 if next_values["offline_enabled"] else 0,
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
            cameras_count = conn.execute(
                "SELECT COUNT(*) AS count FROM cameras WHERE deleted_at IS NULL"
            ).fetchone()["count"]
            online_count = conn.execute(
                "SELECT COUNT(*) AS count FROM cameras WHERE deleted_at IS NULL AND status = 'online'"
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
