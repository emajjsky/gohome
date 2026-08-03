from __future__ import annotations

from pathlib import Path
import re


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
    if 'id="detectionOverlay"' in html:
        raise SystemExit("algorithm console still contains a client composition surface")

    live_loop = function_source(console, "async function loadLiveAnalysis", "async function captureSelected")
    delay = function_source(console, "function liveAnalysisDelay", "function stopLiveAnalysisLoop")
    if "const livePosePollIntervalMs = 200" not in console or "return livePosePollIntervalMs" not in delay:
        raise SystemExit("algorithm console metadata polling is not bounded to a low-overhead cadence")
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
        raise SystemExit("algorithm console is not using the privacy-aware continual pose stream")
    if "poseCompositionOwner" in render_stream or "client" in render_stream:
        raise SystemExit("management console still assigns a client pose composition owner")

    stream_lifecycle = function_source(console, "function frameSequenceForCamera", "function renderStream")
    lifecycle_tokens = [
        "tracking?.source_key",
        "frameSequence < state.lastAnalysisFrameSequence",
        "stream.naturalWidth === 0",
        "renderStream({ retry: true })",
    ]
    if any(token not in stream_lifecycle for token in lifecycle_tokens):
        raise SystemExit("algorithm console cannot recover a stale MJPEG connection after source restart")
    if "ensureLiveStreamLifecycle(cameraId, tracking, frameId)" not in live_loop:
        raise SystemExit("live metadata does not supervise the MJPEG stream lifecycle")

    runtime_metrics = function_source(console, "function runtimeVideoMetrics", "function renderStreamHealth")
    for token in ("stage_latency_ms", "accepted_fps", "source_to_cloud_ms_p95"):
        if token not in runtime_metrics:
            raise SystemExit(f"management console is missing measured video metric: {token}")

    forbidden_client_composition = (
        "poseCompositionOwner",
        "function renderPoseSkeleton",
        'class="pose-skeleton',
        'class="pose-keypoint',
        "renderDetectionOverlay",
    )
    if any(token in console for token in forbidden_client_composition):
        raise SystemExit("management console still contains client-side frame composition")
    if any(token in console_css for token in ("pose-skeleton", "pose-keypoint", "--console-pose")):
        raise SystemExit("management console still ships client-side skeleton styles")

    safety_state = function_source(console, "function unifiedSafetyState", "const postureLabels")
    priority_tokens = [
        "if (analysis.black_screen)",
        'if (fallRuntime.stage === "confirmed")',
        "if (fallReview)",
        "if (personCount > 0 || poses.length > 0)",
    ]
    priority_positions = [safety_state.index(token) for token in priority_tokens]
    if priority_positions != sorted(priority_positions):
        raise SystemExit("primary safety status priority is not deterministic")
    expected_css_asset = re.search(r'/admin/console\.css\?v=([^"\']+)', (ROOT / "admin" / "index.html").read_text(encoding="utf-8"))
    expected_js_asset = re.search(r'/admin/console\.js\?v=([^"\']+)', (ROOT / "admin" / "index.html").read_text(encoding="utf-8"))
    if not expected_css_asset or not expected_js_asset or expected_css_asset.group(1) != expected_js_asset.group(1):
        raise SystemExit("index.html must load one matching console asset version")
    expected_asset_version = expected_css_asset.group(1)
    for page in ("index.html", "algorithms.html", "events.html", "cameras.html"):
        page_html = (ROOT / "admin" / page).read_text(encoding="utf-8")
        if '/admin/console.css' not in page_html:
            raise SystemExit(f"{page} does not load the shared management-console stylesheet")
        if f'/admin/console.css?v={expected_asset_version}' not in page_html:
            raise SystemExit(f"{page} does not load the current management-console stylesheet")
        if f'/admin/console.js?v={expected_asset_version}' not in page_html:
            raise SystemExit(f"{page} does not load the current management-console script")
    if "gradient" in console_css:
        raise SystemExit("management-console stylesheet must not rely on decorative gradients")
    if "function ensureVideoPrivacyControl" not in console:
        raise SystemExit("management console has no shared privacy control")
    if console.count('class="segmented-control privacy-mode-control"') != 1:
        raise SystemExit("privacy controls must be generated from one shared definition")
    privacy_poll = function_source(console, "state.privacyTimer = setInterval", "setInterval(renderPairingCountdown")
    if "pageName" in privacy_poll or "loadVideoPrivacyMode" not in privacy_poll:
        raise SystemExit("privacy state is not synchronized on every management page")

    display_poses = function_source(console, "function snapshotDisplayPoses", "function isPresenceCandidate")
    if '"coasting"' not in display_poses:
        raise SystemExit("algorithm console hides bounded coasting overlays")
    status = function_source(console, "function renderContinualPoseStatus", "function renderDetectionSummary")
    if 'coasting: "短暂补偿"' not in status:
        raise SystemExit("algorithm console does not identify display-only coasting")

    print({
        "ok": True,
        "continuous_video_base": True,
        "single_pose_composition_owner": True,
        "server_composed_skeleton": True,
        "analysis_jpeg_swap_removed": True,
        "stable_stream_status": True,
        "stream_restart_recovery": True,
        "bounded_coasting_visible": True,
        "deterministic_safety_priority": True,
        "shared_console_design_system": True,
        "shared_privacy_control": True,
    })


if __name__ == "__main__":
    main()
