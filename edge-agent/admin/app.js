const state = {
  cameras: [],
  selectedCameraId: null,
  eventFilter: "open",
  detectorBackend: "basic",
  cameraMode: "lan",
  livePreview: true,
  enhancePreview: true,
  liveTimer: null,
  liveRefreshInFlight: false,
  latestSnapshot: null,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

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

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function showToast(message) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
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

function normalizeStreamUrl(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  try {
    const url = new URL(text);
    const path = url.pathname || "/";
    return `${url.protocol}//${url.host}${path}${url.search}`.toLowerCase();
  } catch {
    return text.toLowerCase();
  }
}

function isLocalStreamUrl(value) {
  const streamUrl = String(value ?? "").trim().toLowerCase();
  return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
}

function isLocalCamera(camera) {
  return isLocalStreamUrl(camera?.stream_url);
}

function cameraRank(camera) {
  let rank = 0;
  if (camera.enabled) rank += 40;
  if (!isLocalCamera(camera)) rank += 30;
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

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.dataset.originalText ??= button.innerHTML;
  button.innerHTML = busy ? '<span class="material-symbols-outlined">progress_activity</span>处理中' : button.dataset.originalText;
}

async function loadDevice() {
  const device = await api("/api/device");
  $("apiUrl").textContent = device.api_base_url || "-";
  $("dataDir").textContent = device.data_dir || "-";
  $("detectorBackend").textContent = device.detector_backend || "-";
  state.detectorBackend = device.detector_backend || "basic";
  $("notifyChannel").textContent = device.notify_channel || "off";
  $("workerBadge").textContent = device.worker_running ? "worker 运行中" : "worker 已停止";
  $("workerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  renderDetectorCapability();
}

function renderDetectorCapability() {
  if (!$("personDetectionEnabled")) return;
  const yoloEnabled = state.detectorBackend === "yolo";
  $("personDetectionEnabled").disabled = !yoloEnabled;
  $("personDetectionMirror").disabled = !yoloEnabled;
  $("noPersonMirror").disabled = !yoloEnabled;
  $("fallDetectionMirror").disabled = !yoloEnabled;
  $("personDetectionSwitch").classList.toggle("disabled", !yoloEnabled);
  $("personMirrorRow").classList.toggle("disabled", !yoloEnabled);
  $("noPersonMirrorRow").classList.toggle("disabled", !yoloEnabled);
  $("fallMirrorRow").classList.toggle("disabled", !yoloEnabled);
  $("personMirrorHint").textContent = yoloEnabled ? "当前由 YOLO 执行" : "需要以 YOLO 模式启动";
  $("noPersonMirrorHint").textContent = yoloEnabled ? "达到无人阈值后生成告警" : "需要 YOLO 人数结果";
  $("fallMirrorHint").textContent = yoloEnabled ? "当前由 YOLO 人框比例执行" : "需要以 YOLO 模式启动";
}

async function loadCameras(options = {}) {
  const { preferNetwork = false } = options;
  state.cameras = await api("/api/cameras");
  const selected = state.cameras.find((camera) => camera.id === state.selectedCameraId);
  const hasEnabledNetworkCamera = state.cameras.some((camera) => camera.enabled && !isLocalCamera(camera));
  if (
    !selected ||
    preferNetwork ||
    !selected.enabled ||
    (hasEnabledNetworkCamera && isLocalCamera(selected))
  ) {
    state.selectedCameraId = preferredCameraId(state.cameras);
  }
  renderCameras();
  if (state.selectedCameraId) {
    await loadSnapshot(state.selectedCameraId).catch(() => renderEmptySnapshot());
  } else {
    renderEmptySnapshot();
  }
}

function renderCameras() {
  const list = $("cameraList");
  if (!state.cameras.length) {
    list.innerHTML = '<div class="empty-state">还没有摄像头。先添加局域网摄像头。</div>';
    return;
  }

  list.innerHTML = state.cameras.map((camera) => {
    const rowClass = [
      "camera-row",
      camera.id === state.selectedCameraId ? "active" : "",
      camera.enabled ? "" : "disabled",
    ].filter(Boolean).join(" ");
    const typeLabel = isLocalCamera(camera) ? "本机" : "局域网";
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
        <button class="secondary-button" type="button" data-action="test" data-id="${camera.id}">测试</button>
        <button class="ghost-button" type="button" data-action="capture" data-id="${camera.id}">抓帧</button>
        <button class="ghost-button" type="button" data-action="toggle" data-id="${camera.id}" data-enabled="${camera.enabled ? "1" : "0"}">${camera.enabled ? "禁用" : "启用"}</button>
        <button class="ghost-button danger" type="button" data-action="delete" data-id="${camera.id}">删除</button>
      </div>
    </article>
  `;
  }).join("");
}

function statusText(status) {
  if (status === "online") return "在线";
  if (status === "offline") return "离线";
  if (status === "error") return "错误";
  return "未知";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildLanRtspUrl() {
  const host = $("cameraHost").value.trim();
  const port = $("cameraPort").value.trim() || "554";
  let path = $("cameraPath").value.trim() || "/";
  if (!path.startsWith("/")) path = `/${path}`;
  if (!host) return "";
  return `rtsp://${host}:${port}${path}`;
}

function cameraPayloadFromForm() {
  const name = $("cameraName").value.trim();
  const room = $("cameraRoom").value.trim();
  if (state.cameraMode === "lan") {
    const streamUrl = buildLanRtspUrl();
    if (!streamUrl) {
      throw new Error("请填写摄像头 IP");
    }
    return {
      name: name || "局域网摄像头",
      room,
      stream_url: streamUrl,
      username: $("cameraUsername").value.trim() || null,
      password: $("cameraPassword").value || null,
      enabled: true,
    };
  }

  return {
    name: name || (state.cameraMode === "local" ? "笔记本摄像头" : "RTSP 摄像头"),
    room,
    stream_url: $("cameraUrl").value.trim(),
    username: null,
    password: null,
    enabled: true,
  };
}

function syncLanUrlPreview() {
  if (state.cameraMode === "lan") {
    $("cameraUrl").value = buildLanRtspUrl();
  }
}

function setCameraMode(mode) {
  state.cameraMode = mode;
  $("modeLan").classList.toggle("active", mode === "lan");
  $("modeRtsp").classList.toggle("active", mode === "rtsp");
  $("quickLocal").classList.toggle("active", mode === "local");

  const lan = mode === "lan";
  $("cameraHostField").classList.toggle("hidden", !lan);
  $("cameraHostField").hidden = !lan;
  $("cameraPortField").classList.toggle("hidden", !lan);
  $("cameraPortField").hidden = !lan;
  $("cameraUserField").classList.toggle("hidden", !lan);
  $("cameraUserField").hidden = !lan;
  $("cameraPasswordField").classList.toggle("hidden", !lan);
  $("cameraPasswordField").hidden = !lan;
  $("cameraPathField").classList.toggle("hidden", !lan);
  $("cameraPathField").hidden = !lan;
  $("cameraUrlField").classList.toggle("hidden", lan);
  $("cameraUrlField").hidden = lan;

  if (mode === "lan") {
    $("cameraName").value = "局域网摄像头";
    $("cameraRoom").value = "客厅";
    $("cameraHost").value ||= "192.168.1.11";
    $("cameraPort").value ||= "554";
    $("cameraUsername").value ||= "admin";
    $("cameraPath").value ||= "/";
    syncLanUrlPreview();
    $("cameraHost").focus();
  }
  if (mode === "rtsp") {
    $("cameraName").value = "RTSP 摄像头";
    $("cameraRoom").value = "客厅";
    $("cameraUrl").value = buildLanRtspUrl();
    $("cameraUrl").focus();
  }
  if (mode === "local") {
    $("cameraName").value = "笔记本摄像头";
    $("cameraRoom").value = "本机测试";
    $("cameraUrl").value = "local:0";
    $("cameraUrl").focus();
  }
}

async function createCamera(payload) {
  return api("/api/cameras", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function findExistingCamera(payload) {
  const target = normalizeStreamUrl(payload.stream_url);
  return state.cameras.find((camera) => normalizeStreamUrl(camera.stream_url) === target);
}

async function disableLocalCamerasExcept(activeCameraId) {
  const localCameras = state.cameras.filter((camera) => (
    camera.id !== activeCameraId &&
    camera.enabled &&
    isLocalCamera(camera)
  ));
  await Promise.all(localCameras.map((camera) => updateCamera(camera.id, { enabled: false })));
}

async function saveCamera(payload) {
  const existing = findExistingCamera(payload);
  const camera = existing
    ? await updateCamera(existing.id, payload)
    : await createCamera(payload);

  if (!isLocalStreamUrl(payload.stream_url)) {
    await disableLocalCamerasExcept(camera.id);
  }
  state.selectedCameraId = camera.id;
  showToast(existing ? "摄像头配置已更新" : "摄像头已保存");
  await loadCameras({ preferNetwork: !isLocalStreamUrl(payload.stream_url) });
  await testCamera(camera.id);
}

async function updateCamera(cameraId, payload) {
  return api(`/api/cameras/${cameraId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function deleteCamera(cameraId) {
  return api(`/api/cameras/${cameraId}`, { method: "DELETE" });
}

async function testCamera(cameraId, button) {
  setBusy(button, true);
  try {
    const result = await api(`/api/cameras/${cameraId}/test`, { method: "POST" });
    state.selectedCameraId = cameraId;
    renderSnapshot(result.snapshot);
    showToast(`抓到 ${result.width}x${result.height} 画面`);
    await loadCameras();
  } finally {
    setBusy(button, false);
  }
}

async function loadSnapshot(cameraId) {
  const snapshot = await api(`/api/cameras/${cameraId}/snapshot/latest`);
  renderSnapshot(snapshot);
  if ($("ruleEvaluation")) {
    loadEvaluation(cameraId).catch(() => renderEmptyEvaluation());
  }
}

function renderSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const image = $("snapshotImage");
  if (image && snapshot.image_url) {
    image.onload = () => renderDetectionOverlay(state.latestSnapshot);
    image.src = `${snapshot.image_url}?t=${Date.now()}`;
    image.classList.toggle("enhanced", state.enhancePreview);
  }
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "none";
  setText("snapshotTime", fmtTime(snapshot.captured_at));
  setText("snapshotBrightness", fmtNumber(snapshot.brightness, 1));
  setText("snapshotMotion", snapshot.motion_score === null ? "-" : fmtNumber(snapshot.motion_score, 4));
  setText("snapshotPeople", snapshot.person_count === null || snapshot.person_count === undefined ? "-" : snapshot.person_count);
  setText("snapshotTags", snapshot.tags?.length ? snapshot.tags.join(", ") : "正常");
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
  if (!stage || !image) return null;
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
  if (!overlay) return;
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
  const target = $("detectionSummary");
  if (!target) return;
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
  target.innerHTML = `
    <span class="status-pill ${levelClass}">${escapeHtml(title)}</span>
    <p>${escapeHtml(details.join(" · "))}</p>
  `;
}

async function loadEvaluation(cameraId) {
  const evaluation = await api(`/api/cameras/${cameraId}/evaluation/latest`);
  renderEvaluation(evaluation);
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

function renderEvaluation(evaluation) {
  if (!$("ruleEvaluation")) return;
  const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
  const state = evaluation?.state || {};
  const hasCandidates = candidates.length > 0;
  const pillClass = hasCandidates ? "bad" : "";
  const pillText = hasCandidates ? `${candidates.length} 个告警候选` : "未命中规则";
  const candidateText = hasCandidates
    ? candidates.map((candidate) => candidate.summary).join("；")
    : "当前检测结果没有生成告警候选";
  const details = [
    `运动 ${state.motion_state || "-"}`,
    `无人 ${fmtDuration(state.no_person_seconds)}`,
    `无变化 ${fmtDuration(state.no_motion_seconds)}`,
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
  if (!$("ruleEvaluation")) return;
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill muted">等待规则</span>
      <p>规则评估会说明当前检测结果是否已经生成告警候选。</p>
    </div>
  `;
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  if ($("snapshotImage")) $("snapshotImage").removeAttribute("src");
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "grid";
  if ($("detectionOverlay")) {
    $("detectionOverlay").innerHTML = "";
    $("detectionOverlay").removeAttribute("style");
  }
  if ($("detectionSummary")) {
    $("detectionSummary").innerHTML = `
      <span class="status-pill muted">等待检测</span>
      <p>最新抽帧摘要会显示在这里。</p>
    `;
  }
  for (const id of ["snapshotTime", "snapshotBrightness", "snapshotMotion", "snapshotPeople", "snapshotTags"]) {
    setText(id, "-");
  }
  renderEmptyEvaluation();
}

async function loadEvents() {
  const params = new URLSearchParams({ limit: "30" });
  if (state.eventFilter === "open") params.set("acknowledged", "false");
  if (state.eventFilter === "done") params.set("acknowledged", "true");
  const events = await api(`/api/events?${params.toString()}`);
  const list = $("eventList");
  if (!events.length) {
    list.innerHTML = '<div class="empty-state">当前筛选下暂无告警事件。</div>';
    return;
  }
  list.innerHTML = events.map((event) => `
    <article class="event-item ${event.acknowledged ? "done" : ""}">
      <div class="event-mark ${event.level === "critical" ? "critical" : ""}"></div>
      <div class="event-body">
        <div class="event-title-row">
          <strong>${escapeHtml(event.summary)}</strong>
          <span>${event.acknowledged ? "已处理" : "未处理"}</span>
        </div>
        <p>${escapeHtml(event.type)} · ${escapeHtml(event.camera_name || "未知摄像头")} · ${fmtTime(event.occurred_at)}</p>
        <div class="event-actions">
          ${event.snapshot_url ? `<button class="ghost-button" type="button" data-event-action="snapshot" data-url="${escapeHtml(event.snapshot_url)}">看截图</button>` : ""}
          ${event.acknowledged
            ? `<button class="ghost-button" type="button" data-event-action="reopen" data-id="${event.id}">恢复未处理</button>`
            : `<button class="secondary-button" type="button" data-event-action="ack" data-id="${event.id}">标记已处理</button>`
          }
          <button class="ghost-button" type="button" data-event-action="false_positive" data-id="${event.id}">误报</button>
        </div>
      </div>
    </article>
  `).join("");
}

async function updateEvent(eventId, payload) {
  await api(`/api/events/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  await loadEvents();
}

async function clearDoneEvents() {
  const result = await api("/api/events?scope=acknowledged", { method: "DELETE" });
  showToast(`已清理 ${result.deleted} 条已处理告警`);
  await loadEvents();
}

async function loadRules() {
  if (!$("captureInterval")) return null;
  const rules = await api("/api/rules");
  $("captureInterval").value = rules.capture_interval_seconds;
  $("noMotionSeconds").value = rules.no_motion_seconds;
  $("noPersonSeconds").value = rules.no_person_seconds;
  $("offlineEnabled").checked = rules.offline_enabled;
  $("offlineMirror").checked = rules.offline_enabled;
  $("blackEnabled").checked = rules.black_screen_enabled;
  $("blackMirror").checked = rules.black_screen_enabled;
  $("noMotionEnabled").checked = rules.no_motion_enabled;
  $("noMotionMirror").checked = rules.no_motion_enabled;
  $("personDetectionEnabled").checked = rules.person_detection_enabled;
  $("personDetectionMirror").checked = rules.person_detection_enabled;
  $("noPersonMirror").checked = rules.person_detection_enabled;
  $("fallDetectionMirror").checked = rules.fall_detection_enabled;
  $("notificationEnabled").checked = rules.notification_enabled;
  renderDetectorCapability();
  return rules;
}

async function loadRuleOverview() {
  const target = $("ruleOverview");
  if (!target) return;
  const rules = await api("/api/rules");
  const yoloEnabled = state.detectorBackend === "yolo";
  const items = [
    ["抽帧间隔", `${rules.capture_interval_seconds} 秒`],
    ["人形检测", rules.person_detection_enabled && yoloEnabled ? "已开启" : "未开启"],
    ["疑似跌倒", rules.fall_detection_enabled && yoloEnabled ? "已开启" : "未开启"],
    ["黑屏/遮挡", rules.black_screen_enabled ? "已开启" : "未开启"],
    ["无变化阈值", `${rules.no_motion_seconds} 秒`],
    ["无人阈值", `${rules.no_person_seconds} 秒`],
  ];
  target.innerHTML = items.map(([label, value]) => `
    <div>
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
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
        fall_detection_enabled: $("fallDetectionMirror").checked && state.detectorBackend === "yolo",
        notification_enabled: $("notificationEnabled").checked,
      }),
    });
    showToast("规则已保存");
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
        title: "回家测试通知",
        body: "edge-agent 管理台触发了一条测试通知",
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
    await loadDevice();
    await loadRuleOverview();
    await loadCameras({ preferNetwork: true });
    await loadEvents();
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
    await loadEvents();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.liveRefreshInFlight = false;
  }
}

function restartLivePreview() {
  clearInterval(state.liveTimer);
  if (!state.livePreview) return;
  state.liveTimer = setInterval(liveCaptureTick, 2500);
}

$("cameraForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  setBusy(button, true);
  try {
    await saveCamera(cameraPayloadFromForm());
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
});

$("modeLan").addEventListener("click", () => setCameraMode("lan"));
$("modeRtsp").addEventListener("click", () => setCameraMode("rtsp"));
$("quickLocal").addEventListener("click", () => {
  setCameraMode("local");
});
["cameraHost", "cameraPort", "cameraPath"].forEach((id) => {
  $(id).addEventListener("input", syncLanUrlPreview);
});

$("cameraList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const cameraId = Number(button.dataset.id);
  state.selectedCameraId = cameraId;
  try {
    if (button.dataset.action === "select") {
      await loadSnapshot(cameraId);
    } else if (button.dataset.action === "test") {
      await testCamera(cameraId, button);
    } else if (button.dataset.action === "capture") {
      await testCamera(cameraId, button);
    } else if (button.dataset.action === "toggle") {
      const enabled = button.dataset.enabled !== "1";
      await updateCamera(cameraId, { enabled });
      showToast(enabled ? "摄像头已启用" : "摄像头已禁用");
      await loadCameras();
    } else if (button.dataset.action === "delete") {
      if (!window.confirm("删除这个摄像头配置？历史截图和告警不会删除。")) return;
      await deleteCamera(cameraId);
      if (state.selectedCameraId === cameraId) state.selectedCameraId = null;
      showToast("摄像头已删除");
      await loadCameras();
    }
  } catch (error) {
    showToast(error.message);
  }
});

on("refreshAll", "click", refreshAll);
on("refreshEvents", "click", () => loadEvents().catch((error) => showToast(error.message)));
on("clearDoneEvents", "click", () => clearDoneEvents().catch((error) => showToast(error.message)));
on("eventFilter", "change", (event) => {
  state.eventFilter = event.target.value;
  loadEvents().catch((error) => showToast(error.message));
});
on("saveRules", "click", (event) => saveRules(event.currentTarget).catch((error) => showToast(error.message)));
on("testNotify", "click", (event) => testNotify(event.currentTarget).catch((error) => showToast(error.message)));
on("enhancePreview", "click", () => {
  state.enhancePreview = !state.enhancePreview;
  $("enhancePreview").classList.toggle("active", state.enhancePreview);
  if ($("snapshotImage")) $("snapshotImage").classList.toggle("enhanced", state.enhancePreview);
});
on("livePreview", "click", () => {
  state.livePreview = !state.livePreview;
  $("livePreview").classList.toggle("active", state.livePreview);
  setText("previewMode", state.livePreview ? "自动刷新" : "手动刷新");
  restartLivePreview();
});
window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));
on("offlineMirror", "change", () => {
  $("offlineEnabled").checked = $("offlineMirror").checked;
});
on("offlineEnabled", "change", () => {
  $("offlineMirror").checked = $("offlineEnabled").checked;
});
on("blackMirror", "change", () => {
  $("blackEnabled").checked = $("blackMirror").checked;
});
on("blackEnabled", "change", () => {
  $("blackMirror").checked = $("blackEnabled").checked;
});
on("noMotionMirror", "change", () => {
  $("noMotionEnabled").checked = $("noMotionMirror").checked;
});
on("noMotionEnabled", "change", () => {
  $("noMotionMirror").checked = $("noMotionEnabled").checked;
});
on("personDetectionEnabled", "change", () => {
  $("personDetectionMirror").checked = $("personDetectionEnabled").checked;
  $("noPersonMirror").checked = $("personDetectionEnabled").checked;
});
on("personDetectionMirror", "change", () => {
  $("personDetectionEnabled").checked = $("personDetectionMirror").checked;
  $("noPersonMirror").checked = $("personDetectionMirror").checked;
});
on("noPersonMirror", "change", () => {
  $("personDetectionEnabled").checked = $("noPersonMirror").checked;
  $("personDetectionMirror").checked = $("noPersonMirror").checked;
});
$("eventList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-event-action]");
  if (!button) return;
  const action = button.dataset.eventAction;
  try {
    if (action === "snapshot") {
      const url = `${button.dataset.url}?t=${Date.now()}`;
      if ($("snapshotImage")) {
        $("snapshotImage").src = url;
        if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "none";
      } else {
        window.open(url, "_blank", "noopener");
      }
      showToast("已打开告警截图");
      return;
    }
    const eventId = Number(button.dataset.id);
    if (action === "ack") {
      await updateEvent(eventId, { acknowledged: true, resolution: "handled" });
      showToast("告警已处理");
    }
    if (action === "reopen") {
      await updateEvent(eventId, { acknowledged: false });
      showToast("已恢复为未处理");
    }
    if (action === "false_positive") {
      await updateEvent(eventId, { acknowledged: true, resolution: "false_positive" });
      showToast("已标记为误报");
    }
  } catch (error) {
    showToast(error.message);
  }
});

setCameraMode("lan");
refreshAll();
restartLivePreview();
setInterval(() => {
  loadEvents().catch(() => {});
  if (state.selectedCameraId) loadSnapshot(state.selectedCameraId).catch(() => {});
}, 8000);
