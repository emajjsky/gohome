import os
from pathlib import Path

from .env_loader import load_env_files


LOADED_ENV_FILES = load_env_files(Path(__file__).resolve().parents[1])


class Settings:
    def __init__(self) -> None:
        self.agent_root = Path(__file__).resolve().parents[1]
        self.project_root = self.agent_root.parent
        self.admin_dir = self.agent_root / "admin"
        self.setup_dir = self.agent_root / "setup"
        self.env_files = [str(path) for path in LOADED_ENV_FILES]

        self.data_dir = Path(os.getenv("GOHOME_AGENT_DATA_DIR", self.agent_root / "data"))
        self.snapshot_dir = self.data_dir / "snapshots"
        self.object_storage_dir = self.data_dir / "object_storage"
        self.releases_dir = self.data_dir / "releases"
        self.app_releases_dir = self.releases_dir / "app"
        self.model_releases_dir = self.releases_dir / "model"
        self.runtime_dir = self.data_dir / "runtime"
        self.app_runtime_dir = self.runtime_dir / "app"
        self.runtime_logs_dir = self.app_runtime_dir / "logs"
        self.db_path = Path(os.getenv("GOHOME_AGENT_DB", self.data_dir / "agent.db"))
        self.object_storage_provider = os.getenv("GOHOME_OBJECT_STORAGE_PROVIDER", "signed-localfs").strip() or "signed-localfs"
        self.object_storage_bucket = os.getenv("GOHOME_OBJECT_STORAGE_BUCKET", "public-media").strip() or "public-media"
        self.media_public_base_url = os.getenv("GOHOME_MEDIA_PUBLIC_BASE_URL", "").strip()
        self.app_server_base_url = os.getenv("GOHOME_APP_SERVER_BASE_URL", "").strip().rstrip("/")
        self.device_api_token = os.getenv("GOHOME_DEVICE_API_TOKEN", "").strip()
        self.require_issued_device_token = os.getenv("GOHOME_REQUIRE_ISSUED_DEVICE_TOKEN", "0") == "1"
        self.lan_pairing_window_seconds = int(os.getenv("GOHOME_LAN_PAIRING_WINDOW_SECONDS", "900"))
        self.config_sync_enabled = os.getenv("GOHOME_CONFIG_SYNC_ENABLED", "1") == "1"
        self.config_sync_interval_seconds = float(os.getenv("GOHOME_CONFIG_SYNC_INTERVAL_SECONDS", "10"))
        self.video_privacy_sync_interval_seconds = float(os.getenv("GOHOME_VIDEO_PRIVACY_SYNC_INTERVAL_SECONDS", "1"))
        self.hailo_segmentation_mode = os.getenv("GOHOME_HAILO_SEGMENTATION_MODE", "auto").strip().lower()
        self.hailo_segmentation_model = os.getenv(
            "GOHOME_HAILO_SEGMENTATION_MODEL",
            "/usr/share/hailo-models/yolov11s_seg_h8.hef",
        ).strip()
        self.hailo_segmentation_confidence = float(os.getenv("GOHOME_HAILO_SEGMENTATION_CONFIDENCE", "0.30"))
        self.hailo_segmentation_anchor_interval_seconds = float(
            os.getenv("GOHOME_HAILO_SEGMENTATION_ANCHOR_INTERVAL_SECONDS", "0.18")
        )
        self.hailo_segmentation_maximum_propagation_seconds = float(
            os.getenv("GOHOME_HAILO_SEGMENTATION_MAXIMUM_PROPAGATION_SECONDS", "0.35")
        )
        self.hailo_segmentation_flow_width = int(
            os.getenv("GOHOME_HAILO_SEGMENTATION_FLOW_WIDTH", "320")
        )
        self.config_sync_request_timeout_seconds = float(os.getenv("GOHOME_CONFIG_SYNC_REQUEST_TIMEOUT_SECONDS", os.getenv("GOHOME_UPLOAD_REQUEST_TIMEOUT_SECONDS", "12")))
        self.config_sync_test_capture_enabled = os.getenv("GOHOME_CONFIG_SYNC_TEST_CAPTURE_ENABLED", "0") == "1"
        self.upload_worker_enabled = os.getenv("GOHOME_UPLOAD_WORKER_ENABLED", "1") == "1"
        self.upload_worker_interval_seconds = float(os.getenv("GOHOME_UPLOAD_WORKER_INTERVAL_SECONDS", "5"))
        self.upload_worker_batch_size = int(os.getenv("GOHOME_UPLOAD_WORKER_BATCH_SIZE", "4"))
        self.upload_request_timeout_seconds = float(os.getenv("GOHOME_UPLOAD_REQUEST_TIMEOUT_SECONDS", "12"))
        self.upload_job_lease_seconds = int(os.getenv("GOHOME_UPLOAD_JOB_LEASE_SECONDS", "120"))
        self.live_relay_enabled = os.getenv("GOHOME_LIVE_RELAY_ENABLED", "1") == "1"
        self.live_relay_fps = int(os.getenv("GOHOME_LIVE_RELAY_FPS", "30"))
        self.live_relay_width = int(os.getenv("GOHOME_LIVE_RELAY_WIDTH", "640"))
        self.live_relay_height = int(os.getenv("GOHOME_LIVE_RELAY_HEIGHT", "360"))
        self.media_publish_base_url = os.getenv("GOHOME_MEDIA_PUBLISH_BASE_URL", "").strip().rstrip("/")
        self.media_publish_ffmpeg_path = os.getenv("GOHOME_MEDIA_PUBLISH_FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg"
        self.media_publish_bitrate_kbps = int(os.getenv("GOHOME_MEDIA_PUBLISH_BITRATE_KBPS", "1200"))
        self.media_publish_write_timeout_seconds = float(
            os.getenv("GOHOME_MEDIA_PUBLISH_WRITE_TIMEOUT_SECONDS", "0.75")
        )
        self.media_publish_startup_timeout_seconds = float(
            os.getenv("GOHOME_MEDIA_PUBLISH_STARTUP_TIMEOUT_SECONDS", "5")
        )
        self.history_retention_hours = int(os.getenv("GOHOME_HISTORY_RETENTION_HOURS", "6"))
        self.history_cleanup_interval_seconds = float(os.getenv("GOHOME_HISTORY_CLEANUP_INTERVAL_SECONDS", "3600"))
        self.history_cleanup_batch_size = int(os.getenv("GOHOME_HISTORY_CLEANUP_BATCH_SIZE", "5000"))
        self.completed_upload_retention_days = int(os.getenv("GOHOME_COMPLETED_UPLOAD_RETENTION_DAYS", "7"))
        self.event_evidence_retention_hours = int(os.getenv("GOHOME_EVENT_EVIDENCE_RETENTION_HOURS", "24"))
        self.local_event_retention_days = int(os.getenv("GOHOME_LOCAL_EVENT_RETENTION_DAYS", "30"))
        self.local_runtime_budget_mb = int(os.getenv("GOHOME_LOCAL_RUNTIME_BUDGET_MB", "2048"))
        self.activity_log_interval_seconds = float(os.getenv("GOHOME_ACTIVITY_LOG_INTERVAL_SECONDS", "600"))
        self.activity_posture_stability_seconds = float(os.getenv("GOHOME_ACTIVITY_POSTURE_STABILITY_SECONDS", "5"))
        self.activity_absence_stability_seconds = float(os.getenv("GOHOME_ACTIVITY_ABSENCE_STABILITY_SECONDS", "15"))
        self.risk_evidence_interval_seconds = float(os.getenv("GOHOME_RISK_EVIDENCE_INTERVAL_SECONDS", "0.5"))
        self.local_storage_high_watermark_percent = float(os.getenv("GOHOME_LOCAL_STORAGE_HIGH_WATERMARK_PERCENT", "70"))
        self.local_storage_critical_percent = float(os.getenv("GOHOME_LOCAL_STORAGE_CRITICAL_PERCENT", "85"))

        self.host = os.getenv("GOHOME_AGENT_HOST", "0.0.0.0")
        self.port = int(os.getenv("GOHOME_AGENT_PORT", "8711"))
        self.disable_worker = os.getenv("GOHOME_AGENT_DISABLE_WORKER", "0") == "1"
        self.app_runtime_watchdog_interval_seconds = float(os.getenv("GOHOME_APP_RUNTIME_WATCHDOG_INTERVAL_SECONDS", "2"))
        self.app_runtime_startup_grace_seconds = float(os.getenv("GOHOME_APP_RUNTIME_STARTUP_GRACE_SECONDS", "2"))
        package_signing_public_key_path = os.getenv("GOHOME_PACKAGE_SIGNING_PUBLIC_KEY_PATH", "").strip()
        self.package_signing_public_key_path = (
            Path(package_signing_public_key_path)
            if package_signing_public_key_path
            else self.data_dir / "trust" / "package-signing-ed25519.pem"
        )
        self.package_max_archive_members = int(os.getenv("GOHOME_PACKAGE_MAX_ARCHIVE_MEMBERS", "4096"))
        self.package_max_artifact_bytes = int(os.getenv("GOHOME_PACKAGE_MAX_ARTIFACT_BYTES", str(50 * 1024 * 1024)))
        self.package_max_expanded_bytes = int(
            os.getenv("GOHOME_PACKAGE_MAX_EXPANDED_BYTES", str(1024 * 1024 * 1024))
        )
        self.thermal_monitor_enabled = os.getenv("GOHOME_THERMAL_MONITOR_ENABLED", "1") == "1"
        self.thermal_warm_temperature_c = float(os.getenv("GOHOME_THERMAL_WARM_TEMPERATURE_C", "72"))
        self.thermal_hot_temperature_c = float(os.getenv("GOHOME_THERMAL_HOT_TEMPERATURE_C", "76"))
        self.thermal_critical_temperature_c = float(os.getenv("GOHOME_THERMAL_CRITICAL_TEMPERATURE_C", "80"))
        self.thermal_sample_interval_seconds = float(os.getenv("GOHOME_THERMAL_SAMPLE_INTERVAL_SECONDS", "2"))
        self.inference_idle_interval_seconds = float(os.getenv("GOHOME_INFERENCE_IDLE_INTERVAL_SECONDS", "1.0"))
        self.inference_active_interval_seconds = float(os.getenv("GOHOME_INFERENCE_ACTIVE_INTERVAL_SECONDS", "0.25"))
        self.inference_risk_interval_seconds = float(os.getenv("GOHOME_INFERENCE_RISK_INTERVAL_SECONDS", "0.16"))
        self.inference_max_starvation_seconds = float(os.getenv("GOHOME_INFERENCE_MAX_STARVATION_SECONDS", "3"))
        self.inference_accelerated_idle_interval_seconds = float(os.getenv("GOHOME_INFERENCE_ACCELERATED_IDLE_INTERVAL_SECONDS", "0.5"))
        self.inference_accelerated_active_interval_seconds = float(os.getenv("GOHOME_INFERENCE_ACCELERATED_ACTIVE_INTERVAL_SECONDS", "0.067"))
        self.inference_accelerated_risk_interval_seconds = float(os.getenv("GOHOME_INFERENCE_ACCELERATED_RISK_INTERVAL_SECONDS", "0.05"))

        self.default_capture_interval_seconds = int(os.getenv("GOHOME_CAPTURE_INTERVAL_SECONDS", "600"))
        self.default_no_motion_seconds = int(os.getenv("GOHOME_NO_MOTION_SECONDS", "300"))
        self.motion_threshold = float(os.getenv("GOHOME_MOTION_THRESHOLD", "0.015"))
        self.black_brightness_threshold = float(os.getenv("GOHOME_BLACK_BRIGHTNESS_THRESHOLD", "18"))
        self.black_contrast_threshold = float(os.getenv("GOHOME_BLACK_CONTRAST_THRESHOLD", "4"))
        self.event_throttle_seconds = int(os.getenv("GOHOME_EVENT_THROTTLE_SECONDS", "300"))
        self.detector_backend = os.getenv("GOHOME_DETECTOR_BACKEND", "basic").lower()
        self.yolo_model = os.getenv("GOHOME_YOLO_MODEL", "yolo11n.pt")
        self.yolo_confidence = float(os.getenv("GOHOME_YOLO_CONFIDENCE", "0.20"))
        self.yolo_imgsz = int(os.getenv("GOHOME_YOLO_IMGSZ", "960"))
        self.pose_enabled = os.getenv("GOHOME_POSE_ENABLED", "0") == "1"
        self.pose_backend = os.getenv("GOHOME_POSE_BACKEND", "rtmpose").strip().lower() or "rtmpose"
        self.pose_mode = os.getenv("GOHOME_POSE_MODE", "lightweight").strip().lower() or "lightweight"
        self.pose_runtime_backend = os.getenv("GOHOME_POSE_RUNTIME_BACKEND", "onnxruntime").strip().lower() or "onnxruntime"
        self.pose_device = os.getenv("GOHOME_POSE_DEVICE", "cpu").strip().lower() or "cpu"
        self.pose_fall_threshold = float(os.getenv("GOHOME_POSE_FALL_THRESHOLD", "0.78"))
        self.pose_fall_min_confidence = float(os.getenv("GOHOME_POSE_FALL_MIN_CONFIDENCE", "0.36"))
        self.pose_fall_min_visible_keypoints = int(os.getenv("GOHOME_POSE_FALL_MIN_VISIBLE_KEYPOINTS", "8"))
        self.pose_fall_min_core_keypoints = int(os.getenv("GOHOME_POSE_FALL_MIN_CORE_KEYPOINTS", "2"))
        self.pose_det_frequency = int(os.getenv("GOHOME_POSE_DET_FREQUENCY", "8"))
        self.pose_min_keypoint_confidence = float(os.getenv("GOHOME_POSE_MIN_KEYPOINT_CONFIDENCE", "0.30"))
        self.pose_max_poses = int(os.getenv("GOHOME_POSE_MAX_POSES", "3"))
        self.pose_tracking = os.getenv("GOHOME_POSE_TRACKING", "0") == "1"
        self.pose_cache_seconds = float(os.getenv("GOHOME_POSE_CACHE_SECONDS", "1.8"))
        self.pose_cache_max_motion = float(os.getenv("GOHOME_POSE_CACHE_MAX_MOTION", "0.06"))
        self.activity_window_seconds = float(os.getenv("GOHOME_ACTIVITY_WINDOW_SECONDS", "30"))
        self.activity_max_samples = int(os.getenv("GOHOME_ACTIVITY_MAX_SAMPLES", "90"))
        self.inference_backend = os.getenv("GOHOME_INFERENCE_BACKEND", "auto").strip().lower() or "auto"
        self.hailo_pose_model = os.getenv("GOHOME_HAILO_POSE_MODEL", "/usr/share/hailo-models/yolov8s_pose_h8.hef").strip()
        self.hailo_pose_confidence = float(os.getenv("GOHOME_HAILO_POSE_CONFIDENCE", "0.25"))
        self.hailo_pose_nms_iou = float(os.getenv("GOHOME_HAILO_POSE_NMS_IOU", "0.70"))
        self.hailo_object_mode = os.getenv("GOHOME_HAILO_OBJECT_MODE", "auto").strip().lower() or "auto"
        self.hailo_object_model = os.getenv("GOHOME_HAILO_OBJECT_MODEL", "/usr/share/hailo-models/yolov8s_h8.hef").strip()
        self.hailo_object_confidence = float(os.getenv("GOHOME_HAILO_OBJECT_CONFIDENCE", "0.30"))
        self.hailo_object_interval_seconds = float(os.getenv("GOHOME_HAILO_OBJECT_INTERVAL_SECONDS", "1.0"))
        self.hailo_retry_seconds = float(os.getenv("GOHOME_HAILO_RETRY_SECONDS", "30"))
        self.context_detection_interval_seconds = float(os.getenv("GOHOME_CONTEXT_DETECTION_INTERVAL_SECONDS", "3"))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.object_storage_dir.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self.app_releases_dir.mkdir(parents=True, exist_ok=True)
        self.model_releases_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.app_runtime_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_logs_dir.mkdir(parents=True, exist_ok=True)
        self.package_signing_public_key_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
