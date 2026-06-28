(function () {
    const state = {
        cameras: [],
        selectedCameraId: null,
    };

    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setBusy(button, busy, label) {
        if (!button) return;
        button.disabled = busy;
        button.dataset.originalText ||= button.innerHTML;
        button.innerHTML = busy
            ? `<span class="material-symbols-outlined text-[18px]">progress_activity</span>${label || "处理中"}`
            : button.dataset.originalText;
    }

    function setResultState(title, text, lastTest = null) {
        setText("connectionResultTitle", title);
        setText("connectionResultText", text);
        if (lastTest) {
            setText("edgeLastTest", lastTest);
        }
    }

    function isLocalCamera(camera) {
        const streamUrl = String(camera?.stream_url || "").toLowerCase();
        return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
    }

    function cameraScore(camera) {
        return (camera.enabled ? 100 : 0) + (camera.status === "online" ? 30 : 0) + (isLocalCamera(camera) ? 0 : 20);
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => cameraScore(b) - cameraScore(a))[0] || null;
    }

    function statusLabel(status) {
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

    function normalizeStreamUrl(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        try {
            const url = new URL(text);
            const path = url.pathname || "/";
            return `${url.protocol}//${url.host}${path}${url.search}`.toLowerCase();
        } catch (_error) {
            return text.toLowerCase();
        }
    }

    function explainCameraError(error) {
        const message = String(error || "").trim();
        const lowered = message.toLowerCase();
        if (!message) {
            return "请检查摄像头 IP、端口、账号、密码和路由器连接。";
        }
        if (lowered.includes("cannot open network stream")) {
            return "本机没有连上这路 RTSP 画面。请检查摄像头 IP、端口、视频路径，以及 Mac 和摄像头是否在同一局域网。";
        }
        if (lowered.includes("opened but no frame was returned")) {
            return "已经连到摄像头，但没有取到首帧。常见原因是账号密码不对、码流路径不对，或摄像头没有打开子码流。";
        }
        if (lowered.includes("timed out")) {
            return "连接超时。请确认摄像头在线、网络可达，并优先使用局域网地址。";
        }
        if (lowered.includes("401") || lowered.includes("unauthorized")) {
            return "账号或密码可能不正确，请重新确认摄像头登录信息。";
        }
        if (lowered.includes("404")) {
            return "视频路径可能不正确，请检查 RTSP 路径。";
        }
        if (lowered.includes("opencv is not installed")) {
            return "本机缺少 OpenCV 运行环境，需要先安装依赖。";
        }
        if (lowered.includes("camera not found")) {
            return "这路摄像头记录不存在，可能已经被删除，请刷新后重试。";
        }
        return message;
    }

    function buildStreamUrl() {
        const host = $("cameraHost").value.trim();
        const port = $("cameraPort").value.trim() || "554";
        let path = $("cameraPath").value.trim() || "/";
        if (!host) throw new Error("请填写摄像头 IP");
        if (!/^\d+$/.test(port)) throw new Error("端口必须是数字");
        if (!path.startsWith("/")) path = `/${path}`;
        return `rtsp://${host}:${port}${path}`;
    }

    function payloadFromForm() {
        return {
            name: $("cameraName").value.trim() || "局域网摄像头",
            room: $("cameraRoom").value.trim() || "客厅",
            stream_url: buildStreamUrl(),
            username: $("cameraUsername").value.trim() || null,
            password: $("cameraPassword").value || null,
            enabled: true,
        };
    }

    function pathWithQuery(url) {
        const pathname = url.pathname || "/";
        return `${pathname}${url.search || ""}` || "/";
    }

    function fillFormFromCamera(camera) {
        if (!camera || isLocalCamera(camera)) return;
        $("cameraName").value = camera.name || "局域网摄像头";
        $("cameraRoom").value = camera.room || "客厅";
        $("cameraUsername").value = camera.username || "admin";
        $("cameraPassword").value = "";
        try {
            const url = new URL(camera.stream_url);
            $("cameraHost").value = url.hostname || "192.168.1.11";
            $("cameraPort").value = url.port || "554";
            $("cameraPath").value = pathWithQuery(url);
        } catch (_error) {
            // Leave current form values in place.
        }
    }

    function sameCamera(payload, camera) {
        return normalizeStreamUrl(payload.stream_url) === normalizeStreamUrl(camera.stream_url);
    }

    async function setCameraEnabled(cameraId, enabled) {
        const target = state.cameras.find((camera) => Number(camera.id) === Number(cameraId));
        if (!target) return;
        if (enabled) {
            const otherEnabled = state.cameras.filter((camera) => camera.enabled && camera.id !== cameraId);
            await Promise.all(otherEnabled.map((camera) => GoHomeEdge.updateCamera(camera.id, { enabled: false })));
            await GoHomeEdge.updateCamera(cameraId, { enabled: true });
        } else {
            await GoHomeEdge.updateCamera(cameraId, { enabled: false });
        }
    }

    async function saveCamera(payload) {
        const existing = state.cameras.find((camera) => sameCamera(payload, camera));
        const camera = existing
            ? await GoHomeEdge.updateCamera(existing.id, payload)
            : await GoHomeEdge.createCamera(payload);
        state.selectedCameraId = camera.id;
        await setCameraEnabled(camera.id, payload.enabled !== false);
        await loadCameras();
        return camera;
    }

    function renderPreview(snapshot, result, title = "画面已接入") {
        const image = $("connectionPreviewImage");
        const empty = $("connectionPreviewEmpty");
        if (snapshot?.image_url) {
            image.src = `${GoHomeEdge.edgeUrl(snapshot.image_url)}?t=${Date.now()}`;
            image.classList.remove("hidden");
            empty.classList.add("hidden");
        }
        const detector = result.analysis?.detector_backend || "basic";
        const personCount = snapshot?.person_count ?? result.analysis?.person_count ?? "-";
        setResultState(title, `${result.width}x${result.height} · ${detector} · 人数 ${personCount}`, "通过");
    }

    function secondaryMeta(camera) {
        if (camera.last_error) {
            return explainCameraError(camera.last_error);
        }
        if (camera.last_seen_at) {
            return `最近成功取帧 ${GoHomeEdge.fmtDateTime(camera.last_seen_at)}`;
        }
        return camera.enabled ? "已启用，等待下一次抓帧。" : "当前未启用，不会参与守护。";
    }

    function renderCameras() {
        const list = $("cameraList");
        const networkCameras = state.cameras.filter((camera) => !isLocalCamera(camera));
        const active = preferredCamera(networkCameras);
        $("edgeCameraCount").textContent = String(networkCameras.length);
        $("cameraListBadge").textContent = networkCameras.length ? `${networkCameras.length} 路` : "未接入";
        setText("edgeActiveRoom", active?.room || active?.name || "-");

        if (!networkCameras.length) {
            list.innerHTML = `
                <div class="app-soft-card bg-white p-5 text-center">
                    <span class="material-symbols-outlined text-primary text-[30px]">add_circle</span>
                    <p class="font-display text-[17px] font-bold text-on-surface mt-2">还没有局域网摄像头</p>
                    <p class="font-sans text-[12px] text-on-surface-variant mt-1">先填写上面的信息并测试画面，确认能取到首帧后再保存。</p>
                </div>
            `;
            return;
        }

        list.innerHTML = networkCameras.map((camera) => {
            const isSelected = camera.id === state.selectedCameraId;
            const badge = camera.enabled ? statusLabel(camera.status) : "已禁用";
            const color = camera.enabled && camera.status === "online" ? "text-[#2d7d5c] bg-[#edf6ee]" : "text-[#c87b2a] bg-[#fff4e8]";
            const toggleLabel = camera.enabled ? "停用" : "设为当前";
            return `
                <article class="app-soft-card bg-white p-4 ${isSelected ? "border-primary/30" : ""}">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <p class="font-display text-[16px] font-bold text-on-surface">${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置")}</p>
                            <p class="font-sans text-[12px] text-on-surface-variant mt-1 break-all">${escapeHtml(camera.stream_url)}</p>
                            <p class="font-sans text-[11px] text-on-surface-variant mt-2 leading-relaxed">${escapeHtml(secondaryMeta(camera))}</p>
                        </div>
                        <span class="px-2.5 py-1 rounded-full ${color} text-[10px] font-bold shrink-0">${badge}</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-3">
                        <button class="h-10 rounded-2xl bg-[#f4f6fb] text-on-surface font-sans text-[12px] font-bold" data-action="load" data-id="${camera.id}">填入表单</button>
                        <button class="h-10 rounded-2xl bg-primary text-white font-sans text-[12px] font-bold" data-action="test" data-id="${camera.id}">测试</button>
                        <button class="h-10 rounded-2xl bg-[#f4f6fb] text-on-surface font-sans text-[12px] font-bold" data-action="toggle" data-id="${camera.id}">${toggleLabel}</button>
                        <button class="h-10 rounded-2xl bg-[#fff4f1] text-[#b55536] font-sans text-[12px] font-bold" data-action="delete" data-id="${camera.id}">删除</button>
                    </div>
                </article>
            `;
        }).join("");
    }

    async function loadCameras() {
        state.cameras = await GoHomeEdge.cameras();
        const networkCameras = state.cameras.filter((camera) => !isLocalCamera(camera));
        const preferred = preferredCamera(networkCameras);
        state.selectedCameraId = state.selectedCameraId || preferred?.id || null;
        renderCameras();
        if (preferred) {
            fillFormFromCamera(preferred);
        }
    }

    async function testSavedCamera(cameraId, button) {
        setBusy(button, true, "测试中");
        try {
            const result = await GoHomeEdge.testCamera(cameraId);
            state.selectedCameraId = cameraId;
            renderPreview(result.snapshot, result);
            await loadCameras();
            return result;
        } finally {
            setBusy(button, false);
        }
    }

    async function testDraftCamera(button) {
        setBusy(button, true, "测试中");
        try {
            const payload = payloadFromForm();
            const result = await GoHomeEdge.testCameraConnection(payload);
            renderPreview(result.snapshot, result, "测试通过");
            return result;
        } finally {
            setBusy(button, false);
        }
    }

    async function initialize() {
        try {
            const health = await GoHomeEdge.connect();
            setText("edgeConnectionStatus", "本机守护服务已连接");
            setText("edgeConnectionSubtitle", `服务地址 ${health.lan_url || GoHomeEdge.apiBase || "本机"}，添加后由这台 Mac 负责拉流和检测。`);
            await loadCameras();
        } catch (error) {
            setText("edgeConnectionStatus", "本机服务未连接");
            setText("edgeConnectionSubtitle", error.message || "启动 edge-agent 后再回来接入摄像头。");
            setText("edgeLastTest", "离线");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initialize();

        $("cameraConnectForm").addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = $("saveCameraButton");
            setBusy(button, true, "保存中");
            try {
                await saveCamera(payloadFromForm());
                setResultState("已保存并启用", "这路摄像头已经写入本机守护服务，后续会作为当前主要守护画面。", "待验证");
            } catch (error) {
                setResultState("保存失败", explainCameraError(error.message), "失败");
            } finally {
                setBusy(button, false);
            }
        });

        $("testCameraButton").addEventListener("click", async (event) => {
            try {
                await testDraftCamera(event.currentTarget);
            } catch (error) {
                setResultState("测试失败", explainCameraError(error.message), "失败");
                setBusy(event.currentTarget, false);
            }
        });

        $("cameraList").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (!button) return;
            const cameraId = Number(button.dataset.id);
            const camera = state.cameras.find((item) => Number(item.id) === cameraId);
            if (!camera) return;

            if (button.dataset.action === "load") {
                fillFormFromCamera(camera);
                state.selectedCameraId = cameraId;
                renderCameras();
                setResultState("已填入表单", "可以直接修改这路摄像头的信息，或重新测试画面。");
                return;
            }

            if (button.dataset.action === "test") {
                try {
                    await testSavedCamera(cameraId, button);
                } catch (error) {
                    setResultState("测试失败", explainCameraError(error.message), "失败");
                }
                return;
            }

            if (button.dataset.action === "toggle") {
                setBusy(button, true, camera.enabled ? "停用中" : "启用中");
                try {
                    await setCameraEnabled(cameraId, !camera.enabled);
                    state.selectedCameraId = !camera.enabled ? cameraId : state.selectedCameraId;
                    await loadCameras();
                    setResultState(
                        camera.enabled ? "已停用" : "已设为当前",
                        camera.enabled ? "这路摄像头已停止参与当前守护。" : "这路摄像头已成为当前启用画面，其它已启用画面已自动停用。"
                    );
                } catch (error) {
                    setResultState("切换失败", explainCameraError(error.message), "失败");
                } finally {
                    setBusy(button, false);
                }
                return;
            }

            if (button.dataset.action === "delete") {
                const confirmed = window.confirm(`确认删除“${camera.name}”吗？删除后需要重新填写摄像头信息。`);
                if (!confirmed) return;
                setBusy(button, true, "删除中");
                try {
                    await GoHomeEdge.deleteCamera(cameraId);
                    if (state.selectedCameraId === cameraId) {
                        state.selectedCameraId = null;
                    }
                    await loadCameras();
                    setResultState("已删除", "这路摄像头已从本机守护服务移除。");
                } catch (error) {
                    setResultState("删除失败", explainCameraError(error.message), "失败");
                } finally {
                    setBusy(button, false);
                }
            }
        });
    });
})();
