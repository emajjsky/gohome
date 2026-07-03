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
    new_password: str = Field(..., min_length=6, max_length=128)


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
    activity_detection_enabled: Optional[bool] = None
    fire_detection_enabled: Optional[bool] = None
    offline_enabled: Optional[bool] = None
    notification_enabled: Optional[bool] = None


class EventUpdate(BaseModel):
    acknowledged: Optional[bool] = None
    resolution: Optional[str] = Field(None, max_length=40)


class NotificationTest(BaseModel):
    title: str = "回家测试通知"
    body: str = "edge-agent 通知链路已触发"
    extra: Dict[str, Any] = Field(default_factory=dict)
    event_id: Optional[int] = Field(default=None, ge=1)
    camera_id: Optional[int] = Field(default=None, ge=1)
    preferred_region: str = Field(default="", max_length=40)
    include_public_links: bool = True


class V1AppPushTokenUpsert(BaseModel):
    family_id: int
    app_install_id: str = Field(..., min_length=1, max_length=120)
    platform: str = Field(default="ios", pattern="^(ios|android)$")
    provider: str = Field(default="apns", pattern="^(apns|fcm)$")
    push_token: str = Field(..., min_length=8, max_length=800)
    device_name: str = Field(default="", max_length=120)
    app_version: str = Field(default="", max_length=40)
    environment: str = Field(default="production", pattern="^(production|sandbox)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1AppPushTest(BaseModel):
    title: str = "回家 App 测试通知"
    body: str = "App 原生通知链路已触发"
    family_id: Optional[int] = Field(default=None, ge=1)
    event_id: Optional[int] = Field(default=None, ge=1)
    camera_id: Optional[int] = Field(default=None, ge=1)
    preferred_region: str = Field(default="", max_length=40)
    extra: Dict[str, Any] = Field(default_factory=dict)


class V1AppPushRelayToken(BaseModel):
    app_install_id: str = Field(default="", max_length=120)
    provider: str = Field(default="apns", pattern="^(apns|fcm)$")
    platform: str = Field(default="ios", pattern="^(ios|android)$")
    environment: str = Field(default="production", pattern="^(production|sandbox)$")
    push_token: str = Field(..., min_length=8, max_length=800)


class V1AppPushRelayRequest(BaseModel):
    tokens: list[V1AppPushRelayToken] = Field(default_factory=list)
    notification: Dict[str, Any] = Field(default_factory=dict)


class UserRegister(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=40)


class UserLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)


class FamilyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class ElderProfileUpsert(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=40)
    relationship: str = Field(default="", max_length=40)
    city: str = Field(default="", max_length=80)
    birthday: str = Field(default="", max_length=40)
    lunar_birthday: str = Field(default="", max_length=40)
    living_status: str = Field(default="", max_length=40)
    primary_room: str = Field(default="", max_length=80)
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    diet_notes: list[str] = Field(default_factory=list)
    health_conditions: list[str] = Field(default_factory=list)
    medication_notes: str = Field(default="", max_length=200)
    routine: Dict[str, Any] = Field(default_factory=dict)
    emergency_contacts: list[str] = Field(default_factory=list)
    home_area: str = Field(default="", max_length=120)
    privacy_level: str = Field(default="family_only", max_length=40)


class CalendarEventCreate(BaseModel):
    elder_id: str = Field(default="elder_primary", min_length=1, max_length=80)
    type: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=80)
    start_at: str = Field(..., min_length=4, max_length=40)
    remind_before_days: list[int] = Field(default_factory=list)
    source: str = Field(default="manual", max_length=40)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageGenerateRequest(BaseModel):
    family_id: Optional[int] = Field(default=None, ge=1)
    elder_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    scenario_types: list[str] = Field(default_factory=list)
    clear_existing: bool = True


class MessageStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|read|done|dismissed)$")


class DeviceBindingCreate(BaseModel):
    family_id: int
    device_id: Optional[str] = Field(None, min_length=1, max_length=120)
    device_name: Optional[str] = Field(None, min_length=1, max_length=80)
    device_type: str = Field(default="edge-agent", min_length=1, max_length=40)
    note: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeviceBindingCodeCreate(BaseModel):
    family_id: int
    expires_in_minutes: int = Field(default=10, ge=1, le=60)
    note: str = Field(default="", max_length=120)


class DeviceTokenExchange(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)
    device_id: Optional[str] = Field(None, min_length=1, max_length=120)
    device_name: Optional[str] = Field(None, min_length=1, max_length=80)
    device_type: str = Field(default="edge-agent", min_length=1, max_length=40)
    note: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeviceHeartbeatIn(BaseModel):
    status: str = Field(default="online", min_length=1, max_length=40)
    app_version: str = Field(default="", max_length=40)
    lan_ip: str = Field(default="", max_length=80)
    api_port: Optional[int] = Field(default=None, ge=1, le=65535)
    extra: Dict[str, Any] = Field(default_factory=dict)


class PlaybackSessionCreate(BaseModel):
    resource_type: str = Field(..., pattern="^(stream|snapshot|asset)$")
    family_id: Optional[int] = Field(default=None, ge=1)
    camera_id: Optional[int] = Field(default=None, ge=1)
    snapshot_path: str = Field(default="", max_length=300)
    asset_id: Optional[int] = Field(default=None, ge=1)
    preferred_region: str = Field(default="", max_length=40)
    require_public: bool = False
    expires_in_seconds: int = Field(default=120, ge=30, le=600)


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


class V1MediaAssetCreate(BaseModel):
    snapshot_path: str = Field(default="", max_length=300)
    event_id: Optional[int] = Field(default=None, ge=1)
    content_type: str = Field(default="image/jpeg", max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1MediaUploadSessionCreate(BaseModel):
    family_id: int
    file_name: str = Field(..., min_length=1, max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    byte_size: int = Field(default=0, ge=0, le=52428800)
    device_id: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1MediaUploadSessionComplete(BaseModel):
    content_type: str = Field(default="", max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1MediaPublicLinkCreate(BaseModel):
    expires_in_seconds: int = Field(default=900, ge=60, le=86400)
    family_id: Optional[int] = Field(default=None, ge=1)
    preferred_region: str = Field(default="", max_length=40)
    require_public: bool = True


class V1VideoServiceNodeUpsert(BaseModel):
    family_id: int
    node_id: str = Field(default="", min_length=1, max_length=120)
    device_id: str = Field(default="", max_length=120)
    node_name: str = Field(default="", max_length=120)
    role: str = Field(default="origin", pattern="^(origin|relay|edge)$")
    region: str = Field(default="local", max_length=40)
    service_url: str = Field(default="", max_length=300)
    media_url: str = Field(default="", max_length=300)
    public_base_url: str = Field(default="", max_length=300)
    health_status: str = Field(default="active", pattern="^(active|degraded|offline)$")
    priority: int = Field(default=100, ge=0, le=100000)
    heartbeat_expires_in_seconds: int = Field(default=300, ge=30, le=86400)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class V1PackageReleaseCreate(BaseModel):
    family_id: int
    asset_id: int = Field(..., ge=1)
    package_type: str = Field(..., pattern="^(app|model)$")
    version: str = Field(..., min_length=1, max_length=80)
    install_strategy: str = Field(default="", pattern="^(|file|archive)$")
    entry_path: str = Field(default="", max_length=300)
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
