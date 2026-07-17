from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent


def main() -> None:
    agent = CameraAgent(Path("/tmp/gohome-live-analysis-frame-sync"))
    camera = {"id": 24, "stream_url": "rtsp://example.invalid/live"}
    frame = np.full((48, 64, 3), 96, dtype=np.uint8)

    agent._store_latest_frame(camera, frame, "test stream")
    first = agent.latest_cached_frame(camera, max_age_seconds=1)
    if first is None:
        raise SystemExit("latest frame cache was not populated")
    if not first.get("frame_id"):
        raise SystemExit("cached frame has no stable frame_id")
    if not first.get("captured_at"):
        raise SystemExit("cached frame has no capture timestamp")
    datetime.fromisoformat(str(first["captured_at"]).replace("Z", "+00:00"))

    second_read = agent.latest_cached_frame(camera, max_age_seconds=1)
    if second_read is None or second_read.get("frame_id") != first.get("frame_id"):
        raise SystemExit("the same cached pixels did not preserve their frame_id")

    agent._store_latest_frame(camera, frame + 1, "test stream")
    next_frame = agent.latest_cached_frame(camera, max_age_seconds=1)
    if next_frame is None or next_frame.get("frame_id") == first.get("frame_id"):
        raise SystemExit("a newly captured frame reused the previous frame_id")

    agent._capture_frame_unlocked = lambda _camera: {
        "frame": frame.copy(),
        "width": 64,
        "height": 48,
        "elapsed_ms": 1,
        "source": "direct capture",
    }
    direct = agent.capture_frame(camera, prefer_cache=False)
    if not direct.get("frame_id") or not direct.get("captured_at"):
        raise SystemExit("direct camera capture lost its generated frame identity")

    image_url = agent.frame_data_url(first["frame"], jpeg_quality=60, max_width=64)
    if not image_url.startswith("data:image/jpeg;base64,"):
        raise SystemExit("analysis frame is not encoded as an embeddable JPEG")

    console_source = (ROOT / "admin" / "console.js").read_text(encoding="utf-8")
    algorithms_source = (ROOT / "admin" / "algorithms.html").read_text(encoding="utf-8")
    main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    tracker_source = (ROOT / "app" / "vision" / "continual_pose_tracker.py").read_text(encoding="utf-8")
    required_console_contracts = [
        '$("mjpegStream")',
        "liveAnalysisGeneration",
        "lastAnalysisCapturedAt",
        "/continual-pose/live?include_frame=false",
        "snapshotDisplayPoses",
        "renderContinualPoseStatus",
    ]
    for contract in required_console_contracts:
        if contract not in console_source:
            raise SystemExit(f"frontend live-frame contract is missing: {contract}")
    if 'id="mjpegStream"' not in algorithms_source or 'id="analysisFrame"' in algorithms_source:
        raise SystemExit("algorithm page does not keep one continuous video base")
    if 'id="continualPoseStatus"' not in algorithms_source:
        raise SystemExit("algorithm page has no continual pose status surface")
    if 'if (pageName === "home" && state.selectedCameraId)' not in console_source:
        raise SystemExit("periodic refresh can still replace the live analysis frame with an old snapshot")
    if '@app.get("/api/cameras/{camera_id}/continual-pose/live")' not in main_source:
        raise SystemExit("continual pose same-frame endpoint is missing")
    if "tracker.latest_frame(camera_id)" not in main_source or 'source = "eacp_same_frame"' not in main_source:
        raise SystemExit("continual pose endpoint is not using the exact tracked frame")
    if "def latest_frame(self, camera_id: int)" not in tracker_source:
        raise SystemExit("continual pose tracker does not expose exact frame bundles")
    if "def latest_metadata(self, camera_id: int)" not in tracker_source:
        raise SystemExit("continual pose tracker does not expose pixel-free overlay metadata")

    print({
        "ok": True,
        "frame_id_stable": True,
        "new_frame_id_unique": True,
        "debug_jpeg_available": True,
        "continuous_video_overlay": True,
        "stale_response_guard": True,
        "continual_pose_same_frame_api": True,
        "management_page_uses_background_eacp": True,
    })


if __name__ == "__main__":
    main()
