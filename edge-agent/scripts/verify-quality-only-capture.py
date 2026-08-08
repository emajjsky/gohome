from __future__ import annotations

from pathlib import Path
import sys
from threading import Lock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent
from app.vision.base import AlgorithmResult


class Quality:
    def analyze(self, frame, _previous_frame, _config):
        return {
            "brightness": 80.0,
            "contrast": 20.0,
            "black_screen": False,
            "motion_score": None,
            "motion_detected": True,
            "tags": [],
            "result": AlgorithmResult(
                algorithm_id="quality",
                label="画面质量",
                status="ok",
                score=0.8,
                level="info",
                summary="画面正常",
                data={"thresholds": {"motion_threshold": 0.015}},
            ),
        }


class Pipeline:
    default_config = {"motion_threshold": 0.015}
    quality = Quality()

    def analyze(self, *_args, **_kwargs):
        raise SystemExit("quality-only capture entered the full vision pipeline")


def main() -> None:
    agent = object.__new__(DetectAgent)
    agent._inference_lock = Lock()
    agent.pipeline = Pipeline()
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    result = agent.analyze_frame_quality(frame)
    if result.get("analysis_mode") != "quality_only":
        raise SystemExit(f"wrong capture analysis mode: {result}")
    if result.get("person_count") is not None or result.get("pose_count") != 0:
        raise SystemExit(f"quality capture exposed detection output: {result}")
    if result.get("algorithm_results", {}).get("quality", {}).get("algorithm_id") != "quality":
        raise SystemExit(f"quality result missing: {result}")

    main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    if "/api/cameras/{camera_id}/analysis/live" in main_source or "def live_camera_analysis" in main_source:
        raise SystemExit("retired direct live-analysis route is still present")
    if "def capture_and_store" in main_source or "_capture_and_store_serialized" in main_source:
        raise SystemExit("retired direct analysis helper is still present")

    print({
        "ok": True,
        "quality_only": True,
        "full_pipeline_not_called": True,
        "direct_live_analysis_removed": True,
    })


if __name__ == "__main__":
    main()
