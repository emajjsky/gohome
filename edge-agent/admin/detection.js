const state = {
  cameras: [],
  selectedCameraId: null,
  detectorBackend: "basic",
  livePreview: true,
  enhancePreview: true,
  liveTimer: null,
  liveRefreshInFlight: false,
  latestSnapshot: null,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);

function on(id, eventName, handler) {
  const element = $(id);
  if (element) element.addEventListener(eventName, handler);
}

function fmtTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(digits);
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "-";
  if (value < 60) return `${value} 秒`;
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.dataset.originalText ??= button.innerHTML;
  button.innerHTML = busy
    ? '<span class="material-symbols-outlined">progress_activity</span>处理中'
    : button.dataset.originalText;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  return data;
}

function isLocalStreamUrl(value) {
  const streamUrl = String(value ?? "").trim().toLowerCase();
  return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
}

function cameraRank(camera) {
  let rank = 0;
  if (camera.enabled) rank += 40;
  if (!isLocalStreamUrl(camera.stream_url)) rank += 30;
  if (camera.status === "online") rank += 20;
  return rank;
}

function preferredCameraId(cameras) {
  const sorted = [...cameras].sort((a, b) => {
    const rankDiff = cameraRank(b) - cameraRank(a);
    return rankDiff || Number(b.id) - Number(a.id);
  });
  return sorted[0]?.id || null;
}

function statusText(status) {
  if (status === "online") return "在线";
  if (status === "offline") return "离线";
  if (status === "error") return "错误";
  return "未知";
}

async function loadDevice() {
  const device = await api("/api/device");
  $("apiUrl").textContent = device.api_base_url || "-";
  $("detectorBackend").textContent = device.detector_backend || "-";
  $("yoloModel").textContent = device.yolo_model || "-";
  $("notifyChannel").textContent = device.notify_channel || "off";
  $("workerBadge").textContent = device.worker_running ? "worker 运行中" : "worker 已停止";
  $("workerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  state.detectorBackend = device.detector_backend || "basic";
  renderDetectorCapability();
}

function renderDetectorCapability() {
  const yoloEnabled = state.detectorBackend === "yolo";
  $("personDetectionEnabled").disabled = !yoloEnabled;
  $("fallDetectionEnabled").disabled = !yoloEnabled;
  $("personDetectionSwitch").classList.toggle("disabled", !yoloEnabled);
  $("fallDetectionSwitch").classList.toggle("disabled", !yoloEnabled);
  $("personCapability").textContent = yoloEnabled ? "当前由 YOLO 人数结果执行。" : "需要以 YOLO 模式启动。";
  $("personCapabilityBadge").textContent = yoloEnabled ? "可用" : "待启用";
  $("fallCapability").textContent = yoloEnabled ? "当前由 YOLO 人框比例执行。" : "需要以 YOLO 模式启动。";
  $("fallCapabilityBadge").textContent = yoloEnabled ? "可用" : "待启用";
}

async function loadCameras() {
  state.cameras = await api("/api/cameras");
  const selected = state.cameras.find((camera) => camera.id === state.selectedCameraId);
  if (!selected || !selected.enabled) {
    state.selectedCameraId = preferredCameraId(state.cameras);
  }
  renderCameraPicker();
  if (state.selectedCameraId) {
    await loadSnapshot(state.selectedCameraId).catch(() => renderEmptySnapshot());
  } else {
    renderEmptySnapshot();
  }
}

function renderCameraPicker() {
  const list = $("cameraPicker");
  if (!state.cameras.length) {
    list.innerHTML = '<div class="empty-state">还没有摄像头。请先回到运行台添加局域网摄像头。</div>';
    return;
  }

  list.innerHTML = state.cameras.map((camera) => {
    const rowClass = [
      "camera-row",
      camera.id === state.selectedCameraId ? "active" : "",
      camera.enabled ? "" : "disabled",
    ].filter(Boolean).join(" ");
    const typeLabel = isLocalStreamUrl(camera.stream_url) ? "本机" : "局域网";
    return `
      <article class="${rowClass}">
        <div>
          <h3>
            ${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置房间")}
            <span class="camera-badge">${typeLabel}</span>
            ${camera.enabled ? "" : '<span class="camera-badge muted">已禁用</span>'}
          </h3>
          <p>${escapeHtml(camera.stream_url)} · ${statusText(camera.status)}${camera.last_error ? ` · ${escapeHtml(camera.last_error)}` : ""}</p>
        </div>
        <div class="row-actions">
          <button class="secondary-button" type="button" data-action="select" data-id="${camera.id}">查看</button>
          <button class="ghost-button" type="button" data-action="capture" data-id="${camera.id}">抓帧</button>
        </div>
      </article>
    `;
  }).join("");
}

async function captureSelected(button) {
  if (!state.selectedCameraId) {
    showToast("请先选择摄像头");
    return;
  }
  setBusy(button, true);
  try {
    const result = await api(`/api/cameras/${state.selectedCameraId}/capture`, { method: "POST" });
    renderSnapshot(result.snapshot);
    await loadEvaluation(state.selectedCameraId).catch(() => renderEmptyEvaluation());
    showToast(`抓到 ${result.width}x${result.height} 画面`);
  } finally {
    setBusy(button, false);
  }
}

async function loadSnapshot(cameraId) {
  const snapshot = await api(`/api/cameras/${cameraId}/snapshot/latest`);
  renderSnapshot(snapshot);
  await loadEvaluation(cameraId).catch(() => renderEmptyEvaluation());
}

function renderSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const image = $("snapshotImage");
  image.onload = () => renderDetectionOverlay(state.latestSnapshot);
  image.src = `${snapshot.image_url}?t=${Date.now()}`;
  image.classList.toggle("enhanced", state.enhancePreview);
  $("snapshotEmpty").style.display = "none";
  $("snapshotTime").textContent = fmtTime(snapshot.captured_at);
  $("snapshotBrightness").textContent = fmtNumber(snapshot.brightness, 1);
  $("snapshotMotion").textContent = snapshot.motion_score === null ? "-" : fmtNumber(snapshot.motion_score, 4);
  $("snapshotPeople").textContent = snapshot.person_count === null || snapshot.person_count === undefined ? "-" : snapshot.person_count;
  $("snapshotTags").textContent = snapshot.tags?.length ? snapshot.tags.join(", ") : "正常";
  renderDetectionSummary(snapshot);
  renderDetectionOverlay(snapshot);
}

function snapshotPeople(snapshot) {
  const people = snapshot?.analysis?.people;
  return Array.isArray(people) ? people : [];
}

function imageFitRect(snapshot) {
  const stage = $("previewStage");
  const image = $("snapshotImage");
  const stageWidth = stage.clientWidth;
  const stageHeight = stage.clientHeight;
  const imageWidth = Number(snapshot?.width || image.naturalWidth || snapshot?.analysis?.image_width || 0);
  const imageHeight = Number(snapshot?.height || image.naturalHeight || snapshot?.analysis?.image_height || 0);
  if (!stageWidth || !stageHeight || !imageWidth || !imageHeight) {
    return null;
  }

  const scale = Math.min(stageWidth / imageWidth, stageHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return {
    left: (stageWidth - width) / 2,
    top: (stageHeight - height) / 2,
    width,
    height,
    imageWidth,
    imageHeight,
  };
}

function renderDetectionOverlay(snapshot) {
  const overlay = $("detectionOverlay");
  const people = snapshotPeople(snapshot);
  const rect = imageFitRect(snapshot);
  if (!snapshot || !rect || !people.length) {
    overlay.innerHTML = "";
    overlay.removeAttribute("style");
    return;
  }

  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.innerHTML = people.map((person, index) => {
    const [x1, y1, x2, y2] = person.bbox || [0, 0, 0, 0];
    const left = clamp((Number(x1) / rect.imageWidth) * 100, 0, 100);
    const top = clamp((Number(y1) / rect.imageHeight) * 100, 0, 100);
    const right = clamp((Number(x2) / rect.imageWidth) * 100, 0, 100);
    const bottom = clamp((Number(y2) / rect.imageHeight) * 100, 0, 100);
    const width = clamp(right - left, 0, 100 - left);
    const height = clamp(bottom - top, 0, 100 - top);
    const label = `人 ${index + 1}${person.confidence ? ` · ${Math.round(person.confidence * 100)}%` : ""}`;
    return `
      <div class="detection-box ${person.fall_candidate ? "fall" : ""}"
        style="left:${left}%;top:${top}%;width:${width}%;height:${height}%">
        <span>${escapeHtml(person.fall_candidate ? `${label} · 疑似跌倒` : label)}</span>
      </div>
    `;
  }).join("");
}

function renderDetectionSummary(snapshot) {
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const personCount = snapshot?.person_count ?? analysis.person_count;
  const blackScreen = Boolean(analysis.black_screen);
  const fallCandidate = Boolean(analysis.fall_candidate);
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const levelClass = fallCandidate || blackScreen ? "bad" : people.length ? "" : "muted";
  const title = fallCandidate ? "疑似跌倒" : blackScreen ? "画面异常" : backend === "yolo" ? "YOLO 已运行" : "基础检测";
  const details = [
    `后端 ${backend}`,
    `人数 ${personCount ?? "-"}`,
    `人框 ${people.length}`,
    `亮度 ${fmtNumber(analysis.brightness ?? snapshot?.brightness, 1)}`,
    `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`,
    fallCandidate ? "命中跌倒候选" : "未命中跌倒候选",
    blackScreen ? "黑屏/遮挡" : "画面正常",
  ];
  $("detectionSummary").innerHTML = `
    <span class="status-pill ${levelClass}">${escapeHtml(title)}</span>
    <p>${escapeHtml(details.join(" · "))}</p>
  `;
}

async function loadEvaluation(cameraId) {
  const evaluation = await api(`/api/cameras/${cameraId}/evaluation/latest`);
  renderEvaluation(evaluation);
}

function renderEvaluation(evaluation) {
  const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
  const evalState = evaluation?.state || {};
  const hasCandidates = candidates.length > 0;
  const pillClass = hasCandidates ? "bad" : "";
  const pillText = hasCandidates ? `${candidates.length} 个告警候选` : "未命中规则";
  const candidateText = hasCandidates
    ? candidates.map((candidate) => candidate.summary).join("；")
    : "当前检测结果没有生成告警候选";
  const details = [
    `运动 ${evalState.motion_state || "-"}`,
    `无人 ${fmtDuration(evalState.no_person_seconds)}`,
    `无变化 ${fmtDuration(evalState.no_motion_seconds)}`,
    `评估 ${fmtTime(evaluation?.evaluated_at)}`,
  ].join(" · ");
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill ${pillClass}">${escapeHtml(pillText)}</span>
      <p><strong>${escapeHtml(candidateText)}</strong><br>${escapeHtml(details)}</p>
    </div>
  `;
}

function renderEmptyEvaluation() {
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill muted">等待规则</span>
      <p>后台 worker 还没有给这个摄像头生成规则评估，抓帧或等待下一轮抽帧。</p>
    </div>
  `;
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  $("snapshotImage").removeAttribute("src");
  $("snapshotEmpty").style.display = "grid";
  $("detectionOverlay").innerHTML = "";
  $("detectionOverlay").removeAttribute("style");
  $("detectionSummary").innerHTML = `
    <span class="status-pill muted">等待检测</span>
    <p>抓帧后会显示 YOLO 人框、置信度、黑屏和运动变化结果。</p>
  `;
  $("snapshotTime").textContent = "-";
  $("snapshotBrightness").textContent = "-";
  $("snapshotMotion").textContent = "-";
  $("snapshotPeople").textContent = "-";
  $("snapshotTags").textContent = "-";
  renderEmptyEvaluation();
}

async function loadRules() {
  const rules = await api("/api/rules");
  $("captureInterval").value = rules.capture_interval_seconds;
  $("noMotionSeconds").value = rules.no_motion_seconds;
  $("noPersonSeconds").value = rules.no_person_seconds;
  $("offlineEnabled").checked = rules.offline_enabled;
  $("blackEnabled").checked = rules.black_screen_enabled;
  $("noMotionEnabled").checked = rules.no_motion_enabled;
  $("personDetectionEnabled").checked = rules.person_detection_enabled;
  $("fallDetectionEnabled").checked = rules.fall_detection_enabled;
  $("notificationEnabled").checked = rules.notification_enabled;
  renderDetectorCapability();
}

async function saveRules(button) {
  setBusy(button, true);
  try {
    await api("/api/rules", {
      method: "PUT",
      body: JSON.stringify({
        capture_interval_seconds: Number($("captureInterval").value),
        no_motion_seconds: Number($("noMotionSeconds").value),
        no_person_seconds: Number($("noPersonSeconds").value),
        offline_enabled: $("offlineEnabled").checked,
        black_screen_enabled: $("blackEnabled").checked,
        no_motion_enabled: $("noMotionEnabled").checked,
        person_detection_enabled: $("personDetectionEnabled").checked && state.detectorBackend === "yolo",
        fall_detection_enabled: $("fallDetectionEnabled").checked && state.detectorBackend === "yolo",
        notification_enabled: $("notificationEnabled").checked,
      }),
    });
    showToast("检测规则已保存");
    if (state.selectedCameraId) {
      await loadEvaluation(state.selectedCameraId).catch(() => renderEmptyEvaluation());
    }
  } finally {
    setBusy(button, false);
  }
}

async function testNotify(button) {
  setBusy(button, true);
  try {
    const result = await api("/api/notify/test", {
      method: "POST",
      body: JSON.stringify({
        title: "想家了吗测试通知",
        body: "edge-agent 检测页触发了一条测试通知",
      }),
    });
    $("notifyResult").textContent = result.sent ? "测试通知已发送。" : `未发送：${result.reason || "通知通道未启用"}`;
    showToast(result.sent ? "测试通知已发送" : "通知通道未启用");
  } finally {
    setBusy(button, false);
  }
}

async function refreshAll() {
  try {
    await Promise.all([loadDevice(), loadRules()]);
    await loadCameras();
  } catch (error) {
    showToast(error.message);
  }
}

async function liveCaptureTick() {
  if (!state.livePreview || !state.selectedCameraId) return;
  if (state.liveRefreshInFlight) return;
  state.liveRefreshInFlight = true;
  try {
    await loadSnapshot(state.selectedCameraId);
  } catch {
    renderEmptySnapshot();
  } finally {
    state.liveRefreshInFlight = false;
  }
}

function restartLivePreview() {
  clearInterval(state.liveTimer);
  if (!state.livePreview) return;
  state.liveTimer = setInterval(liveCaptureTick, 2500);
}

on("refreshAll", "click", refreshAll);
on("saveRules", "click", (event) => saveRules(event.currentTarget).catch((error) => showToast(error.message)));
on("testNotify", "click", (event) => testNotify(event.currentTarget).catch((error) => showToast(error.message)));
on("captureSelected", "click", (event) => captureSelected(event.currentTarget).catch((error) => showToast(error.message)));
on("enhancePreview", "click", () => {
  state.enhancePreview = !state.enhancePreview;
  $("enhancePreview").classList.toggle("active", state.enhancePreview);
  $("snapshotImage").classList.toggle("enhanced", state.enhancePreview);
});
on("livePreview", "click", () => {
  state.livePreview = !state.livePreview;
  $("livePreview").classList.toggle("active", state.livePreview);
  $("previewMode").textContent = state.livePreview ? "自动刷新" : "手动刷新";
  restartLivePreview();
});

$("cameraPicker").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const cameraId = Number(button.dataset.id);
  state.selectedCameraId = cameraId;
  renderCameraPicker();
  try {
    if (button.dataset.action === "select") {
      await loadSnapshot(cameraId);
    }
    if (button.dataset.action === "capture") {
      await captureSelected(button);
    }
  } catch (error) {
    showToast(error.message);
  }
});

window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));

refreshAll();
restartLivePreview();
