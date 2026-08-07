from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1)
    room: str = ""
    stream_url: str = Field(..., min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    room: Optional[str] = None
    stream_url: Optional[str] = Field(None, min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: Optional[bool] = None


class WifiConnectRequest(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=80)
    password: str = Field(default="", max_length=128)


class AdminLogin(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=40)
    password: str = Field(..., min_length=1, max_length=128)


class AdminPasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=10, max_length=128)


class VideoPrivacyUpdate(BaseModel):
    minimum_mode: str = Field(default="original", pattern="^(original|person_blur|skeleton)$")


class CameraOut(BaseModel):
    id: int
    name: str
    room: str
    stream_url: str
    username: Optional[str] = None
    enabled: bool
    status: str
    last_seen_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str
    updated_at: str


class RulesUpdate(BaseModel):
    capture_interval_seconds: Optional[int] = Field(None, ge=1, le=3600)
    motion_threshold: Optional[float] = Field(None, ge=0, le=1)
    black_brightness_threshold: Optional[float] = Field(None, ge=0, le=255)
    black_contrast_threshold: Optional[float] = Field(None, ge=0, le=255)
    yolo_confidence: Optional[float] = Field(None, ge=0.01, le=1)
    no_motion_seconds: Optional[int] = Field(None, ge=10, le=86400)
    no_person_seconds: Optional[int] = Field(None, ge=10, le=86400)
    black_screen_enabled: Optional[bool] = None
    no_motion_enabled: Optional[bool] = None
    person_detection_enabled: Optional[bool] = None
    fall_detection_enabled: Optional[bool] = None
    fall_score_threshold: Optional[float] = Field(None, ge=0, le=1)
    fall_confirm_frames: Optional[int] = Field(None, ge=1, le=120)
    fall_confirm_seconds: Optional[int] = Field(None, ge=0, le=300)
    fall_recover_frames: Optional[int] = Field(None, ge=1, le=120)
    activity_detection_enabled: Optional[bool] = None
    offline_enabled: Optional[bool] = None


class EventUpdate(BaseModel):
    acknowledged: Optional[bool] = None
    resolution: Optional[str] = Field(None, max_length=40)


class DeviceHeartbeatIn(BaseModel):
    status: str = Field(default="online", min_length=1, max_length=40)
    app_version: str = Field(default="", max_length=40)
    lan_ip: str = Field(default="", max_length=80)
    api_port: Optional[int] = Field(default=None, ge=1, le=65535)
    extra: Dict[str, Any] = Field(default_factory=dict)


class V1DeviceEventIngest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=120)
    event_type: str = Field(..., min_length=1, max_length=60)
    summary: str = Field(..., min_length=1, max_length=200)
    level: str = Field(default="warning", min_length=1, max_length=20)
    room: str = Field(default="", max_length=80)
    camera_id: Optional[int] = Field(default=None, ge=1)
    snapshot_path: str = Field(default="", max_length=300)
    occurred_at: str = Field(default="", max_length=40)
    payload: Dict[str, Any] = Field(default_factory=dict)


class V1PackageArtifactUploadCreate(BaseModel):
    family_id: int
    file_name: str = Field(..., min_length=1, max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    byte_size: int = Field(..., ge=1, le=52428800)
    device_id: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1PackageArtifactUploadComplete(BaseModel):
    content_type: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1PackageArtifactPublicLinkCreate(BaseModel):
    expires_in_seconds: int = Field(default=900, ge=60, le=86400)


class V1PackageReleaseCreate(BaseModel):
    family_id: int
    asset_id: int = Field(..., ge=1)
    manifest_version: int = Field(default=1, ge=1, le=1)
    package_type: str = Field(..., pattern="^(app|model)$")
    version: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    device_scope: str = Field(default="family", pattern="^(family|device)$")
    device_id: str = Field(default="", max_length=120)
    byte_size: int = Field(..., ge=1, le=52428800)
    sha256: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$")
    signature_key_id: str = Field(..., pattern=r"^[0-9a-fA-F]{16}$")
    signature: str = Field(..., min_length=80, max_length=128)
    install_strategy: str = Field(..., pattern="^(file|archive)$")
    entry_type: str = Field(..., pattern="^(python|shell|executable|data)$")
    entry_path: str = Field(..., min_length=1, max_length=300)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1PackageDownloadLinkCreate(BaseModel):
    expires_in_seconds: int = Field(default=900, ge=60, le=86400)


class V1DeviceUpgradeRun(BaseModel):
    package_types: list[str] = Field(default_factory=list)


class V1DeviceSyncTargetUpdate(BaseModel):
    desired_app_version: str = Field(default="", max_length=40)
    desired_model_version: str = Field(default="", max_length=80)
    rules: Optional[RulesUpdate] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class V1DeviceSyncReport(BaseModel):
    app_version: str = Field(default="", max_length=40)
    model_version: str = Field(default="", max_length=80)
    applied_rule_version: str = Field(default="", max_length=80)
    worker_running: Optional[bool] = None
    runtime: Dict[str, Any] = Field(default_factory=dict)
    status: Dict[str, Any] = Field(default_factory=dict)


class V1DeviceRolloutCreate(BaseModel):
    family_id: int
    title: str = Field(default="", max_length=80)
    rollout_mode: str = Field(default="canary", pattern="^(canary|full)$")
    device_ids: list[str] = Field(default_factory=list)
    canary_device_ids: list[str] = Field(default_factory=list)
    desired_app_version: str = Field(default="", max_length=40)
    desired_model_version: str = Field(default="", max_length=80)
    rules: Optional[RulesUpdate] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class V1DeviceRolloutPromote(BaseModel):
    device_ids: list[str] = Field(default_factory=list)


class V1DeviceRolloutRollback(BaseModel):
    device_ids: list[str] = Field(default_factory=list)
