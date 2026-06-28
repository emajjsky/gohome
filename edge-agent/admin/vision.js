const state = {
  cameras: [],
  selectedCameraId: null,
  detectorBackend: "basic",
  latestSnapshot: null,
  latestEvaluation: null,
  refreshTimer: null,
  streamMaskTimer: null,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "-";
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "-";
  if (value < 60) return `${Math.round(value)} 秒`;
  const minutes = Math.floor(value / 60);
  const rest = Math.round(value % 60);
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}

function tagLabel(tag) {
  const labels = {
    black_screen: "黑屏/遮挡",
    low_motion: "低变化",
    person_detected: "检测到人",
    no_person_detected: "暂未检测到人",
    fall_candidate: "疑似跌倒候选",
  };
  return labels[tag] || tag;
}

function showToast(message) {
  const toast = $("toast");
  if (!toast) return;
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
  return (camera.enabled ? 100 : 0) + (camera.status === "online" ? 30 : 0) + (isLocalStreamUrl(camera.stream_url) ? 0 : 20);
}

function preferredCameraId(cameras) {
  return [...cameras].sort((a, b) => cameraRank(b) - cameraRank(a) || Number(b.id) - Number(a.id))[0]?.id || null;
}

function selectedCamera() {
  return state.cameras.find((camera) => Number(camera.id) === Number(state.selectedCameraId)) || null;
}

function statusText(status) {
  if (status === "online") return "在线";
  if (status === "offline") return "离线";
  if (status === "error") return "错误";
  return "未知";
}

function statusClass(status) {
  if (status === "online") return "";
  if (status === "offline" || status === "error") return "bad";
  return "muted";
}

function snapshotPeople(snapshot) {
  const people = snapshot?.analysis?.people;
  return Array.isArray(people) ? people : [];
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function imageFitRect(snapshot) {
  const stage = $("previewStage");
  const image = $("snapshotImage");
  if (!stage || !image) return null;
  const stageWidth = stage.clientWidth;
  const stageHeight = stage.clientHeight;
  const imageWidth = Number(snapshot?.width || image.naturalWidth || snapshot?.analysis?.image_width || 0);
  const imageHeight = Number(snapshot?.height || image.naturalHeight || snapshot?.analysis?.image_height || 0);
  if (!stageWidth || !stageHeight || !imageWidth || !imageHeight) return null;

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

async function loadDevice() {
  const device = await api("/api/device");
  state.detectorBackend = device.detector_backend || "basic";
  setText("apiUrl", device.api_base_url || "-");
  setText("detectorBackend", device.detector_backend || "-");
  setText("yoloModel", device.yolo_model || "-");
  setText("notifyChannel", device.notify_channel || "off");
  setText("workerBadge", device.worker_running ? "worker 运行中" : "worker 已停止");
  setText("overviewWorker", device.worker_running ? "运行中" : "已停止");
  setText("overviewBackend", device.detector_backend || "-");
  setText("overviewModel", device.yolo_model || "basic");
  if ($("workerBadge")) {
    $("workerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  }
  renderCapabilityState();
}

function renderCapabilityState() {
  const yoloEnabled = state.detectorBackend === "yolo";
  setText("personCapability", yoloEnabled ? "当前可读取 YOLO 人数和检测框。" : "需要以 YOLO 模式启动。");
  setText("fallCapability", yoloEnabled ? "当前可读取 YOLO 人框比例候选。" : "需要以 YOLO 模式启动。");
  setText("personCapabilityBadge", yoloEnabled ? "可用" : "待启用");
  setText("fallCapabilityBadge", yoloEnabled ? "可用" : "待启用");
  for (const id of ["personDetectionEnabled", "fallDetectionEnabled"]) {
    if ($(id)) $(id).disabled = !yoloEnabled;
  }
}

async function loadCameras() {
  state.cameras = await api("/api/cameras");
  if (!selectedCamera()) {
    state.selectedCameraId = preferredCameraId(state.cameras);
  }
  renderCameraControls();
  renderStream();
  if (state.selectedCameraId) {
    await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
  } else {
    renderEmptySnapshot();
    renderEmptyEvaluation();
  }
}

function renderCameraControls() {
  const select = $("cameraSelect");
  if (select) {
    select.innerHTML = state.cameras.length
      ? state.cameras.map((camera) => `
        <option value="${camera.id}" ${Number(camera.id) === Number(state.selectedCameraId) ? "selected" : ""}>
          ${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置")} · ${statusText(camera.status)}
        </option>
      `).join("")
      : '<option value="">还没有摄像头</option>';
  }

  const list = $("cameraPicker");
  if (list) {
    if (!state.cameras.length) {
      list.innerHTML = '<div class="empty-state">还没有摄像头。请先回到运行台添加 local:0 或 RTSP 摄像头。</div>';
    } else {
      list.innerHTML = state.cameras.map((camera) => {
        const active = Number(camera.id) === Number(state.selectedCameraId);
        const typeLabel = isLocalStreamUrl(camera.stream_url) ? "本机" : "局域网";
        return `
          <article class="camera-row ${active ? "active" : ""} ${camera.enabled ? "" : "disabled"}">
            <div>
              <h3>${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置")} <span class="camera-badge">${typeLabel}</span></h3>
              <p>${escapeHtml(camera.stream_url)} · ${statusText(camera.status)}${camera.last_error ? ` · ${escapeHtml(camera.last_error)}` : ""}</p>
            </div>
            <div class="row-actions">
              <button class="secondary-button" type="button" data-action="select" data-id="${camera.id}">选择</button>
              <button class="ghost-button" type="button" data-action="capture" data-id="${camera.id}">抓帧</button>
            </div>
          </article>
        `;
      }).join("");
    }
  }

  setText("overviewCameraCount", state.cameras.length ? `${state.cameras.length} 路` : "未接入");
}

function renderStream() {
  const stream = $("mjpegStream");
  if (!stream) return;
  const empty = $("streamEmpty");
  const camera = selectedCamera();
  clearTimeout(state.streamMaskTimer);
  if (!camera) {
    stream.removeAttribute("src");
    if (empty) {
      empty.style.display = "grid";
      empty.querySelector("p").textContent = "请选择摄像头";
    }
    setText("streamStatus", "未选择摄像头");
    setText("streamCamera", "无摄像头");
    return;
  }
  if (empty) {
    empty.style.display = "grid";
    empty.querySelector("p").textContent = "视频流加载中";
  }
  stream.onload = () => {
    if (empty) empty.style.display = "none";
    setText("streamStatus", "MJPEG 视频流");
  };
  stream.onerror = () => {
    clearTimeout(state.streamMaskTimer);
    if (empty) {
      empty.style.display = "grid";
      empty.querySelector("p").textContent = "视频流暂不可用";
    }
    setText("streamStatus", "视频流不可用");
  };
  stream.src = `/api/cameras/${camera.id}/stream.mjpg?fps=6&t=${Date.now()}`;
  state.streamMaskTimer = setTimeout(() => {
    if (stream.getAttribute("src") && empty) empty.style.display = "none";
  }, 900);
  setText("streamStatus", "MJPEG 视频流");
  setText("streamCamera", `${camera.name} · ${camera.room || "未设置"}`);
  setText("streamUrl", `/api/cameras/${camera.id}/stream.mjpg`);
}

function renderSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const tags = Array.isArray(snapshot?.tags) ? snapshot.tags : [];
  const image = $("snapshotImage");
  if (image && snapshot.image_url) {
    image.onload = () => renderDetectionOverlay(state.latestSnapshot);
    image.src = `${snapshot.image_url}?t=${Date.now()}`;
  }
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "none";

  setText("snapshotTime", fmtTime(snapshot.captured_at));
  setText("snapshotBrightness", fmtNumber(snapshot.brightness, 1));
  setText("snapshotMotion", snapshot.motion_score === null ? "-" : fmtNumber(snapshot.motion_score, 4));
  setText("snapshotPeople", snapshot.person_count === null || snapshot.person_count === undefined ? "-" : snapshot.person_count);
  setText("snapshotTags", tags.length ? tags.map(tagLabel).join("，") : "正常");
  setText("overviewSnapshotTime", fmtTime(snapshot.captured_at));
  setText("streamFrameTime", fmtTime(snapshot.captured_at));

  renderDetectionOverlay(snapshot);
  renderQualityAlgorithm(snapshot);
  renderPersonAlgorithm(snapshot);
  renderFallAlgorithm(snapshot);
  renderDetectionSummary(snapshot);
}

function renderDetectionSummary(snapshot) {
  const target = $("detectionSummary");
  if (!target) return;
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const fallCandidate = Boolean(analysis.fall_candidate);
  const blackScreen = Boolean(analysis.black_screen);
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const levelClass = fallCandidate || blackScreen ? "bad" : people.length ? "" : "muted";
  const title = fallCandidate ? "疑似跌倒" : blackScreen ? "画面异常" : backend === "yolo" ? "YOLO 已运行" : "基础检测";
  const details = [
    `后端 ${backend}`,
    `人数 ${snapshot?.person_count ?? analysis.person_count ?? "-"}`,
    `人框 ${people.length}`,
    `亮度 ${fmtNumber(analysis.brightness ?? snapshot?.brightness, 1)}`,
    `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`,
  ];
  target.innerHTML = `<span class="status-pill ${levelClass}">${escapeHtml(title)}</span><p>${escapeHtml(details.join(" · "))}</p>`;
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  if ($("snapshotImage")) $("snapshotImage").removeAttribute("src");
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "grid";
  if ($("detectionOverlay")) $("detectionOverlay").innerHTML = "";
  for (const id of ["snapshotTime", "snapshotBrightness", "snapshotMotion", "snapshotPeople", "snapshotTags"]) {
    setText(id, "-");
  }
}

async function loadSnapshot(cameraId) {
  const snapshot = await api(`/api/cameras/${cameraId}/snapshot/latest`);
  renderSnapshot(snapshot);
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
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    showToast(`抓到 ${result.width}x${result.height} 画面`);
  } finally {
    setBusy(button, false);
  }
}

function renderQualityAlgorithm(snapshot) {
  const analysis = snapshot?.analysis || {};
  setText("qualityBrightness", fmtNumber(analysis.brightness ?? snapshot?.brightness, 1));
  setText("qualityContrast", fmtNumber(analysis.contrast, 1));
  setText("qualityMotion", analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4));
  setText("qualityBlackScreen", analysis.black_screen ? "命中" : "未命中");
  setText("qualityMotionState", analysis.motion_detected ? "有变化" : "低变化");
}

function renderPersonAlgorithm(snapshot) {
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  setText("personBackend", analysis.detector_backend || state.detectorBackend || "basic");
  setText("personCount", snapshot?.person_count ?? analysis.person_count ?? "-");
  setText("personBoxes", people.length ? `${people.length} 个` : "-");
  const list = $("personBoxList");
  if (list) {
    list.innerHTML = people.length ? people.map((person, index) => `
      <div class="detect-row">
        <div>
          <strong>人框 ${index + 1}</strong>
          <span>置信度 ${person.confidence ? Math.round(person.confidence * 100) + "%" : "-"} · 宽高比 ${person.aspect_ratio ?? "-"} · 面积 ${person.area_ratio ?? "-"}</span>
        </div>
        <em>${person.fall_candidate ? "疑似跌倒" : "正常"}</em>
      </div>
    `).join("") : '<div class="empty-state">当前截图没有 YOLO 人框。</div>';
  }
}

function renderFallAlgorithm(snapshot) {
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const candidates = people.filter((person) => person.fall_candidate);
  setText("fallStatus", analysis.fall_candidate ? "命中候选" : "未命中");
  setText("fallCandidateCount", candidates.length ? `${candidates.length} 个` : "0 个");
  setText("fallBackend", analysis.detector_backend || state.detectorBackend || "basic");
  const evidence = $("fallEvidence");
  if (evidence) {
    evidence.innerHTML = candidates.length ? candidates.map((person, index) => `
      <div class="algorithm-row">
        <strong>候选 ${index + 1}</strong>
        <p>宽高比 ${person.aspect_ratio ?? "-"}，面积占比 ${person.area_ratio ?? "-"}，高度占比 ${person.height_ratio ?? "-"}，中心位置 ${person.center_y_ratio ?? "-"}。</p>
        <span class="status-pill bad">需要确认</span>
      </div>
    `).join("") : `
      <div class="algorithm-row">
        <strong>当前截图</strong>
        <p>未出现满足宽高比、面积、低位和高度约束的人框。</p>
        <span class="status-pill muted">未命中</span>
      </div>
    `;
  }
}

async function loadEvaluation(cameraId) {
  const evaluation = await api(`/api/cameras/${cameraId}/evaluation/latest`);
  state.latestEvaluation = evaluation;
  renderEvaluation(evaluation);
}

function renderEvaluation(evaluation) {
  const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
  const evalState = evaluation?.state || {};
  const hasCandidates = candidates.length > 0;
  setText("evaluationState", hasCandidates ? `${candidates.length} 个候选` : "未命中规则");
  setText("evaluationSummary", hasCandidates ? candidates.map((candidate) => candidate.summary).join("；") : "当前检测结果没有生成告警候选。");
  setText("noPersonSeconds", fmtDuration(evalState.no_person_seconds));
  setText("noMotionSecondsMetric", fmtDuration(evalState.no_motion_seconds));
  setText("evaluationTime", fmtTime(evaluation?.evaluated_at));
  const badge = $("evaluationBadge");
  if (badge) {
    badge.textContent = hasCandidates ? "有候选" : "未命中";
    badge.className = `status-pill ${hasCandidates ? "bad" : ""}`;
  }
}

function renderEmptyEvaluation() {
  setText("evaluationState", "等待规则");
  setText("evaluationSummary", "后台 worker 还没有生成规则评估，抓帧或等待下一轮抽帧。");
  setText("noPersonSeconds", "-");
  setText("noMotionSecondsMetric", "-");
  setText("evaluationTime", "-");
}

async function loadRules() {
  const rules = await api("/api/rules");
  if ($("captureInterval")) $("captureInterval").value = rules.capture_interval_seconds;
  if ($("noMotionSeconds")) $("noMotionSeconds").value = rules.no_motion_seconds;
  if ($("noPersonSecondsInput")) $("noPersonSecondsInput").value = rules.no_person_seconds;
  if ($("offlineEnabled")) $("offlineEnabled").checked = rules.offline_enabled;
  if ($("blackEnabled")) $("blackEnabled").checked = rules.black_screen_enabled;
  if ($("noMotionEnabled")) $("noMotionEnabled").checked = rules.no_motion_enabled;
  if ($("personDetectionEnabled")) $("personDetectionEnabled").checked = rules.person_detection_enabled;
  if ($("fallDetectionEnabled")) $("fallDetectionEnabled").checked = rules.fall_detection_enabled;
  if ($("notificationEnabled")) $("notificationEnabled").checked = rules.notification_enabled;
  setText("ruleCaptureInterval", `${rules.capture_interval_seconds} 秒`);
  setText("ruleNoMotion", `${rules.no_motion_seconds} 秒`);
  setText("ruleNoPerson", `${rules.no_person_seconds} 秒`);
  setText("ruleNotify", rules.notification_enabled ? "开启" : "关闭");
}

async function saveRules(button) {
  setBusy(button, true);
  try {
    await api("/api/rules", {
      method: "PUT",
      body: JSON.stringify({
        capture_interval_seconds: Number($("captureInterval").value),
        no_motion_seconds: Number($("noMotionSeconds").value),
        no_person_seconds: Number($("noPersonSecondsInput").value),
        offline_enabled: $("offlineEnabled").checked,
        black_screen_enabled: $("blackEnabled").checked,
        no_motion_enabled: $("noMotionEnabled").checked,
        person_detection_enabled: $("personDetectionEnabled").checked && state.detectorBackend === "yolo",
        fall_detection_enabled: $("fallDetectionEnabled").checked && state.detectorBackend === "yolo",
        notification_enabled: $("notificationEnabled").checked,
      }),
    });
    await loadRules();
    showToast("检测规则已保存");
  } finally {
    setBusy(button, false);
  }
}

async function refreshAll() {
  try {
    await Promise.all([loadDevice(), loadRules().catch(() => null)]);
    await loadCameras();
  } catch (error) {
    showToast(error.message || "无法连接 edge-agent");
  }
}

function bindEvents() {
  if ($("refreshAll")) $("refreshAll").addEventListener("click", refreshAll);
  if ($("captureSelected")) $("captureSelected").addEventListener("click", (event) => captureSelected(event.currentTarget).catch((error) => showToast(error.message)));
  if ($("saveRules")) $("saveRules").addEventListener("click", (event) => saveRules(event.currentTarget).catch((error) => showToast(error.message)));
  if ($("cameraSelect")) {
    $("cameraSelect").addEventListener("change", async (event) => {
      state.selectedCameraId = Number(event.currentTarget.value);
      renderCameraControls();
      renderStream();
      await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
      await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    });
  }
  if ($("cameraPicker")) {
    $("cameraPicker").addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      state.selectedCameraId = Number(button.dataset.id);
      renderCameraControls();
      renderStream();
      if (button.dataset.action === "capture") {
        await captureSelected(button).catch((error) => showToast(error.message));
      } else {
        await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
        await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
      }
    });
  }
  window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshAll();
  state.refreshTimer = setInterval(() => {
    if (state.selectedCameraId) {
      loadSnapshot(state.selectedCameraId).catch(() => null);
      loadEvaluation(state.selectedCameraId).catch(() => null);
    }
  }, 6000);
});
