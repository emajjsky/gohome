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
    offline_enabled: Optional[bool] = None
    notification_enabled: Optional[bool] = None


class EventUpdate(BaseModel):
    acknowledged: Optional[bool] = None
    resolution: Optional[str] = Field(None, max_length=40)


class NotificationTest(BaseModel):
    title: str = "想家了吗测试通知"
    body: str = "edge-agent 通知链路已触发"
    extra: Dict[str, Any] = Field(default_factory=dict)
