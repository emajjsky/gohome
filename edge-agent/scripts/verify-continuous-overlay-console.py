from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def function_source(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def main() -> None:
    html = (ROOT / "admin" / "algorithms.html").read_text(encoding="utf-8")
    console = (ROOT / "admin" / "console.js").read_text(encoding="utf-8")

    if html.count('id="mjpegStream"') != 1 or 'id="detectionOverlay"' not in html:
        raise SystemExit("algorithm console must have one continuous video base and one overlay")
    if 'id="analysisFrame"' in html:
        raise SystemExit("algorithm console still swaps the video base for analysis JPEGs")

    live_loop = function_source(console, "async function loadLiveAnalysis", "async function captureSelected")
    delay = function_source(console, "function liveAnalysisDelay", "function stopLiveAnalysisLoop")
    if "return 750" not in delay:
        raise SystemExit("algorithm console metadata polling must use a controlled 750ms cadence")
    if "include_frame=false" not in live_loop:
        raise SystemExit("algorithm console does not poll lightweight overlay metadata")
    if "include_frame=true" in live_loop:
        raise SystemExit("algorithm console still downloads analysis JPEGs during live display")
    if 'setText("streamStatus", "实时分析中")' in live_loop:
        raise SystemExit("metadata polling still flashes a request-in-progress label")
    if live_loop.count('setText("streamStatus", "后台连续感知")') != 1:
        raise SystemExit("algorithm console does not expose one stable continual sensing label")
    if 'document.addEventListener("visibilitychange"' not in console:
        raise SystemExit("algorithm console does not pause and resume metadata updates with page visibility")

    render_snapshot = function_source(console, "function renderSnapshot", "function renderContinualPoseStatus")
    if 'removeAttribute("src")' in render_snapshot or '$("analysisFrame")' in render_snapshot:
        raise SystemExit("rendering metadata can still stop or replace the continuous video")

    render_stream = function_source(console, "function renderStream", "function snapshotPeople")
    if '$("analysisFrame")' in render_stream:
        raise SystemExit("stream lifecycle still depends on the removed analysis image")

    display_poses = function_source(console, "function snapshotDisplayPoses", "function snapshotPoseEdges")
    if '"coasting"' not in display_poses:
        raise SystemExit("algorithm console hides bounded coasting overlays")
    status = function_source(console, "function renderContinualPoseStatus", "function renderDetectionSummary")
    if 'coasting: "等待模型锚点"' not in status:
        raise SystemExit("algorithm console does not identify display-only coasting")

    print({
        "ok": True,
        "continuous_video_base": True,
        "metadata_overlay_only": True,
        "analysis_jpeg_swap_removed": True,
        "stable_stream_status": True,
        "bounded_coasting_visible": True,
    })


if __name__ == "__main__":
    main()
