from pathlib import Path
import os


class Settings:
    def __init__(self) -> None:
        self.agent_root = Path(__file__).resolve().parents[1]
        self.project_root = self.agent_root.parent
        self.frontend_dir = self.project_root
        self.admin_dir = self.agent_root / "admin"

        self.data_dir = Path(os.getenv("GOHOME_AGENT_DATA_DIR", self.agent_root / "data"))
        self.snapshot_dir = self.data_dir / "snapshots"
        self.db_path = Path(os.getenv("GOHOME_AGENT_DB", self.data_dir / "agent.db"))

        self.host = os.getenv("GOHOME_AGENT_HOST", "0.0.0.0")
        self.port = int(os.getenv("GOHOME_AGENT_PORT", "8711"))
        self.disable_worker = os.getenv("GOHOME_AGENT_DISABLE_WORKER", "0") == "1"

        self.default_capture_interval_seconds = int(os.getenv("GOHOME_CAPTURE_INTERVAL_SECONDS", "5"))
        self.default_no_motion_seconds = int(os.getenv("GOHOME_NO_MOTION_SECONDS", "300"))
        self.motion_threshold = float(os.getenv("GOHOME_MOTION_THRESHOLD", "0.015"))
        self.black_brightness_threshold = float(os.getenv("GOHOME_BLACK_BRIGHTNESS_THRESHOLD", "18"))
        self.black_contrast_threshold = float(os.getenv("GOHOME_BLACK_CONTRAST_THRESHOLD", "4"))
        self.event_throttle_seconds = int(os.getenv("GOHOME_EVENT_THROTTLE_SECONDS", "300"))
        self.detector_backend = os.getenv("GOHOME_DETECTOR_BACKEND", "basic").lower()
        self.yolo_model = os.getenv("GOHOME_YOLO_MODEL", "yolov8n.pt")
        self.yolo_confidence = float(os.getenv("GOHOME_YOLO_CONFIDENCE", "0.35"))

        self.notify_channel = os.getenv("GOHOME_NOTIFY_CHANNEL", "off").lower()
        self.generic_webhook_url = os.getenv("GOHOME_GENERIC_WEBHOOK_URL", "")
        self.feishu_webhook = os.getenv("GOHOME_FEISHU_WEBHOOK", "")
        self.bark_url = os.getenv("GOHOME_BARK_URL", "")
        self.telegram_bot_token = os.getenv("GOHOME_TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("GOHOME_TELEGRAM_CHAT_ID", "")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
