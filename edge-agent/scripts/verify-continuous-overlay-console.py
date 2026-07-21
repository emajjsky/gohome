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
    console_css = (ROOT / "admin" / "console.css").read_text(encoding="utf-8")

    if html.count('id="mjpegStream"') != 1:
        raise SystemExit("algorithm console must have one continuous video base")
    if 'id="analysisFrame"' in html:
        raise SystemExit("algorithm console still swaps the video base for analysis JPEGs")

    live_loop = function_source(console, "async function loadLiveAnalysis", "async function captureSelected")
    delay = function_source(console, "function liveAnalysisDelay", "function stopLiveAnalysisLoop")
    if "return 500" not in delay:
        raise SystemExit("algorithm console metadata polling must use a controlled 500ms cadence")
    if "include_frame=false" not in live_loop:
        raise SystemExit("algorithm console does not poll lightweight overlay metadata")
    if "include_frame=true" in live_loop:
        raise SystemExit("algorithm console still downloads analysis JPEGs during live display")
    if 'setText("streamStatus", "实时分析中")' in live_loop:
        raise SystemExit("metadata polling still flashes a request-in-progress label")
    if 'document.addEventListener("visibilitychange"' not in console:
        raise SystemExit("algorithm console does not pause and resume metadata updates with page visibility")

    render_snapshot = function_source(console, "function renderSnapshot", "function renderContinualPoseStatus")
    if 'removeAttribute("src")' in render_snapshot or '$("analysisFrame")' in render_snapshot:
        raise SystemExit("rendering metadata can still stop or replace the continuous video")

    render_stream = function_source(console, "function renderStream", "function snapshotPeople")
    if '$("analysisFrame")' in render_stream:
        raise SystemExit("stream lifecycle still depends on the removed analysis image")
    if "/continual-pose/stream.mjpg" not in render_stream:
        raise SystemExit("algorithm console is not using the synchronized server-side pose stream")

    render_overlay = function_source(console, "function renderDetectionOverlay", "function renderPoseSkeleton")
    if "serverAnnotated" not in render_overlay:
        raise SystemExit("algorithm console can still draw a second asynchronous pose overlay")
    if "analysis.fire_candidate || analysis.fire_event_candidate" in render_overlay:
        raise SystemExit("weak fire evidence can still replace the primary overlay status")

    safety_state = function_source(console, "function unifiedSafetyState", "function overlayPeopleForMode")
    priority_tokens = [
        "if (analysis.black_screen)",
        'if (fallRuntime.stage === "confirmed")',
        "if (fallReview)",
        "if (hasConfirmedFireEvent())",
        "if (analysis.fire_event_candidate)",
        "if (personCount > 0 || poses.length > 0)",
    ]
    priority_positions = [safety_state.index(token) for token in priority_tokens]
    if priority_positions != sorted(priority_positions):
        raise SystemExit("primary safety status priority is not deterministic")
    if safety_state.index("analysis.fire_candidate") < safety_state.index("if (personCount > 0 || poses.length > 0)"):
        raise SystemExit("weak fire evidence still outranks normal person activity")

    for page in ("index.html", "algorithms.html", "events.html", "cameras.html"):
        page_html = (ROOT / "admin" / page).read_text(encoding="utf-8")
        if '/admin/console.css' not in page_html:
            raise SystemExit(f"{page} does not load the shared management-console stylesheet")
    if "gradient" in console_css:
        raise SystemExit("management-console stylesheet must not rely on decorative gradients")

    display_poses = function_source(console, "function snapshotDisplayPoses", "function snapshotPoseEdges")
    if '"coasting"' not in display_poses:
        raise SystemExit("algorithm console hides bounded coasting overlays")
    status = function_source(console, "function renderContinualPoseStatus", "function renderDetectionSummary")
    if 'coasting: "短暂补偿"' not in status:
        raise SystemExit("algorithm console does not identify display-only coasting")

    print({
        "ok": True,
        "continuous_video_base": True,
        "synchronized_server_overlay": True,
        "analysis_jpeg_swap_removed": True,
        "stable_stream_status": True,
        "bounded_coasting_visible": True,
        "deterministic_safety_priority": True,
        "shared_console_design_system": True,
    })


if __name__ == "__main__":
    main()
