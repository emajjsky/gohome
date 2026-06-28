from __future__ import annotations

from typing import Any, Dict
import socket

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .camera_agent import CameraAgent, CameraError
from .detect_agent import DetectAgent
from .event_agent import EventAgent
from .notifier import Notifier
from .schemas import CameraCreate, CameraUpdate, EventUpdate, NotificationTest, RulesUpdate
from .settings import settings
from .storage import Storage
from .worker import EdgeWorker


def model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


settings.ensure_dirs()
storage = Storage(settings.db_path)
camera_agent = CameraAgent(settings.snapshot_dir)
detect_agent = DetectAgent(
    black_brightness_threshold=settings.black_brightness_threshold,
    black_contrast_threshold=settings.black_contrast_threshold,
    motion_threshold=settings.motion_threshold,
    detector_backend=settings.detector_backend,
    yolo_model=settings.yolo_model,
    yolo_confidence=settings.yolo_confidence,
)
notifier = Notifier(settings)
event_agent = EventAgent(storage, notifier, settings.event_throttle_seconds)
worker = EdgeWorker(storage, camera_agent, detect_agent, event_agent)

app = FastAPI(title="gohome edge-agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/snapshots", StaticFiles(directory=str(settings.snapshot_dir)), name="snapshots")
app.mount("/admin", StaticFiles(directory=str(settings.admin_dir), html=True), name="admin")
app.mount("/ui", StaticFiles(directory=str(settings.frontend_dir), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/index.html")


@app.on_event("startup")
def on_startup() -> None:
    storage.init_schema()
    if not settings.disable_worker:
        worker.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    worker.stop()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "gohome-edge-agent",
        "worker_running": worker.is_running,
        "lan_url": f"http://{local_ip()}:{settings.port}",
    }


@app.get("/api/device")
def device() -> Dict[str, Any]:
    return {
        "name": socket.gethostname(),
        "lan_ip": local_ip(),
        "api_port": settings.port,
        "api_base_url": f"http://{local_ip()}:{settings.port}",
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
        "snapshot_dir": str(settings.snapshot_dir),
        "notify_channel": settings.notify_channel,
        "detector_backend": settings.detector_backend,
        "yolo_model": settings.yolo_model if settings.detector_backend == "yolo" else None,
        "worker_running": worker.is_running,
    }


@app.get("/api/cameras")
def list_cameras() -> list[Dict[str, Any]]:
    return storage.list_cameras()


@app.post("/api/cameras")
def create_camera(camera: CameraCreate) -> Dict[str, Any]:
    return storage.create_camera(model_dump(camera))


@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.patch("/api/cameras/{camera_id}")
def update_camera(camera_id: int, patch: CameraUpdate) -> Dict[str, Any]:
    camera = storage.update_camera(camera_id, model_dump(patch))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int) -> Dict[str, Any]:
    deleted = storage.delete_camera(camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"deleted": True, "camera_id": camera_id}


def capture_and_store(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        rules = storage.get_rules()
        capture = camera_agent.capture_frame(camera)
        analysis = detect_agent.analyze_frame_with_config(capture["frame"], config=rules)
        relative_path = camera_agent.snapshot_relative_path(camera_id)
        camera_agent.save_frame(capture["frame"], relative_path)
        snapshot = storage.create_snapshot(
            camera_id=camera_id,
            image_path=relative_path,
            width=capture["width"],
            height=capture["height"],
            brightness=analysis["brightness"],
            motion_score=analysis["motion_score"],
            tags=analysis["tags"],
            person_count=analysis.get("person_count"),
            analysis=analysis,
        )
        storage.update_camera_status(camera_id, "online")
        return {
            "ok": True,
            "camera_id": camera_id,
            "width": capture["width"],
            "height": capture["height"],
            "elapsed_ms": capture["elapsed_ms"],
            "source": capture["source"],
            "snapshot": snapshot,
            "analysis": analysis,
        }
    except CameraError as exc:
        storage.update_camera_status(camera_id, "offline", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cameras/{camera_id}/test")
async def test_camera(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(capture_and_store, camera_id)


@app.post("/api/cameras/{camera_id}/capture")
async def capture_camera(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(capture_and_store, camera_id)


@app.get("/api/cameras/{camera_id}/snapshot/latest")
def latest_camera_snapshot(camera_id: int) -> Dict[str, Any]:
    if storage.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    snapshot = storage.latest_snapshot(camera_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@app.get("/api/cameras/{camera_id}/stream.mjpg")
def camera_mjpeg_stream(
    camera_id: int,
    fps: int = 5,
    width: int = 1280,
    height: int = 720,
    quality: int = 70,
    drop: int = 4,
) -> StreamingResponse:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    fps = max(1, min(int(fps), 15))
    width = max(320, min(int(width), 1920))
    height = max(180, min(int(height), 1080))
    quality = max(35, min(int(quality), 95))
    drop = max(0, min(int(drop), 12))
    return StreamingResponse(
        camera_agent.mjpeg_frames(
            camera,
            fps=fps,
            jpeg_quality=quality,
            max_width=width,
            max_height=height,
            drop_stale_frames=drop,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/cameras/{camera_id}/evaluation/latest")
def latest_camera_evaluation(camera_id: int) -> Dict[str, Any]:
    if storage.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    evaluation = worker.latest_evaluations.get(camera_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Rule evaluation not found")
    return evaluation


@app.get("/api/events")
def list_events(limit: int = 50, acknowledged: bool | None = None) -> list[Dict[str, Any]]:
    return storage.list_events(limit=max(1, min(limit, 200)), acknowledged=acknowledged)


@app.get("/api/events/{event_id}")
def get_event(event_id: int) -> Dict[str, Any]:
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.patch("/api/events/{event_id}")
def update_event(event_id: int, patch: EventUpdate) -> Dict[str, Any]:
    event = storage.update_event(event_id, model_dump(patch))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.delete("/api/events")
def clear_events(scope: str = "acknowledged") -> Dict[str, Any]:
    try:
        return storage.clear_events(scope=scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/summary/today")
def today_summary() -> Dict[str, Any]:
    return storage.daily_summary()


@app.get("/api/rules")
def get_rules() -> Dict[str, Any]:
    return storage.get_rules()


@app.put("/api/rules")
def update_rules(rules: RulesUpdate) -> Dict[str, Any]:
    return storage.update_rules(model_dump(rules))


@app.post("/api/notify/test")
def notify_test(message: NotificationTest) -> Dict[str, Any]:
    payload = model_dump(message)
    return notifier.send(payload["title"], payload["body"], payload.get("extra") or {})
