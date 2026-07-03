import os
from pathlib import Path

from .env_loader import load_env_files


LOADED_ENV_FILES = load_env_files(Path(__file__).resolve().parents[1])


class Settings:
    def __init__(self) -> None:
        self.agent_root = Path(__file__).resolve().parents[1]
        self.project_root = self.agent_root.parent
        self.frontend_dir = self.project_root
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
        self.edge_bootstrap_dir = self.runtime_dir / "edge-bootstrap"
        self.edge_bootstrap_logs_dir = self.edge_bootstrap_dir / "logs"
        self.db_path = Path(os.getenv("GOHOME_AGENT_DB", self.data_dir / "agent.db"))
        self.edge_launch_agent_label = os.getenv("GOHOME_EDGE_LAUNCH_AGENT_LABEL", "com.gohome.edge-agent").strip() or "com.gohome.edge-agent"
        self.object_storage_provider = os.getenv("GOHOME_OBJECT_STORAGE_PROVIDER", "signed-localfs").strip() or "signed-localfs"
        self.object_storage_bucket = os.getenv("GOHOME_OBJECT_STORAGE_BUCKET", "public-media").strip() or "public-media"
        self.public_base_url = os.getenv("GOHOME_PUBLIC_BASE_URL", "").strip()
        self.video_service_public_base_url = os.getenv("GOHOME_VIDEO_SERVICE_PUBLIC_BASE_URL", "").strip()
        self.media_public_base_url = os.getenv("GOHOME_MEDIA_PUBLIC_BASE_URL", "").strip()
        self.video_service_node_id = os.getenv("GOHOME_VIDEO_SERVICE_NODE_ID", "").strip()
        self.video_service_region = os.getenv("GOHOME_VIDEO_SERVICE_REGION", "local").strip() or "local"
        self.video_service_role = os.getenv("GOHOME_VIDEO_SERVICE_ROLE", "origin").strip() or "origin"
        self.video_distribution_name = os.getenv("GOHOME_VIDEO_DISTRIBUTION_NAME", "single-origin").strip() or "single-origin"

        self.host = os.getenv("GOHOME_AGENT_HOST", "0.0.0.0")
        self.port = int(os.getenv("GOHOME_AGENT_PORT", "8711"))
        self.disable_worker = os.getenv("GOHOME_AGENT_DISABLE_WORKER", "0") == "1"
        self.app_runtime_watchdog_interval_seconds = float(os.getenv("GOHOME_APP_RUNTIME_WATCHDOG_INTERVAL_SECONDS", "2"))
        self.app_runtime_startup_grace_seconds = float(os.getenv("GOHOME_APP_RUNTIME_STARTUP_GRACE_SECONDS", "2"))

        self.default_capture_interval_seconds = int(os.getenv("GOHOME_CAPTURE_INTERVAL_SECONDS", "5"))
        self.default_no_motion_seconds = int(os.getenv("GOHOME_NO_MOTION_SECONDS", "300"))
        self.motion_threshold = float(os.getenv("GOHOME_MOTION_THRESHOLD", "0.015"))
        self.black_brightness_threshold = float(os.getenv("GOHOME_BLACK_BRIGHTNESS_THRESHOLD", "18"))
        self.black_contrast_threshold = float(os.getenv("GOHOME_BLACK_CONTRAST_THRESHOLD", "4"))
        self.event_throttle_seconds = int(os.getenv("GOHOME_EVENT_THROTTLE_SECONDS", "300"))
        self.detector_backend = os.getenv("GOHOME_DETECTOR_BACKEND", "basic").lower()
        self.yolo_model = os.getenv("GOHOME_YOLO_MODEL", "yolo11n.pt")
        self.yolo_confidence = float(os.getenv("GOHOME_YOLO_CONFIDENCE", "0.20"))
        self.yolo_imgsz = int(os.getenv("GOHOME_YOLO_IMGSZ", "960"))
        self.enable_demo_camera = os.getenv("GOHOME_ENABLE_DEMO_CAMERA", "0") == "1"

        self.notify_channel = os.getenv("GOHOME_NOTIFY_CHANNEL", "off").lower()
        self.generic_webhook_url = os.getenv("GOHOME_GENERIC_WEBHOOK_URL", "")
        self.feishu_webhook = os.getenv("GOHOME_FEISHU_WEBHOOK", "")
        self.bark_url = os.getenv("GOHOME_BARK_URL", "")
        self.telegram_bot_token = os.getenv("GOHOME_TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("GOHOME_TELEGRAM_CHAT_ID", "")
        self.app_push_provider = os.getenv("GOHOME_APP_PUSH_PROVIDER", "off").strip().lower() or "off"
        self.app_push_relay_url = os.getenv("GOHOME_APP_PUSH_RELAY_URL", "").strip()
        self.app_push_relay_secret = os.getenv("GOHOME_APP_PUSH_RELAY_SECRET", "").strip()
        self.app_deep_link_scheme = os.getenv("GOHOME_APP_DEEP_LINK_SCHEME", "gohome").strip() or "gohome"
        self.apns_auth_key_path = os.getenv("GOHOME_APNS_AUTH_KEY_PATH", "").strip()
        self.apns_key_id = os.getenv("GOHOME_APNS_KEY_ID", "").strip()
        self.apns_team_id = os.getenv("GOHOME_APNS_TEAM_ID", "").strip()
        self.apns_topic = os.getenv("GOHOME_APNS_TOPIC", "").strip()
        self.apns_default_environment = os.getenv("GOHOME_APNS_DEFAULT_ENVIRONMENT", "production").strip().lower() or "production"
        self.apns_request_timeout_seconds = float(os.getenv("GOHOME_APNS_REQUEST_TIMEOUT_SECONDS", "8"))

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
        self.edge_bootstrap_dir.mkdir(parents=True, exist_ok=True)
        self.edge_bootstrap_logs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
