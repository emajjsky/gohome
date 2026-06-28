(function () {
    const state = {
        cameras: [],
        selectedCameraId: null,
        busy: false,
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

    function buildStreamUrl() {
        const host = $("cameraHost").value.trim();
        const port = $("cameraPort").value.trim() || "554";
        let path = $("cameraPath").value.trim() || "/";
        if (!path.startsWith("/")) path = `/${path}`;
        if (!host) throw new Error("请填写摄像头 IP");
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

    function fillFormFromCamera(camera) {
        if (!camera || isLocalCamera(camera)) return;
        $("cameraName").value = camera.name || "局域网摄像头";
        $("cameraRoom").value = camera.room || "客厅";
        $("cameraUsername").value = camera.username || "admin";
        try {
            const url = new URL(camera.stream_url);
            $("cameraHost").value = url.hostname || "192.168.1.11";
            $("cameraPort").value = url.port || "554";
            $("cameraPath").value = url.pathname || "/";
        } catch (_error) {
            // Leave current form values in place.
        }
    }

    function sameCamera(payload, camera) {
        return normalizeStreamUrl(payload.stream_url) === normalizeStreamUrl(camera.stream_url);
    }

    async function disableOtherLocalCameras(activeCameraId) {
        const localCameras = state.cameras.filter((camera) => camera.enabled && camera.id !== activeCameraId && isLocalCamera(camera));
        await Promise.all(localCameras.map((camera) => GoHomeEdge.updateCamera(camera.id, { enabled: false })));
    }

    async function saveCamera(payload) {
        const existing = state.cameras.find((camera) => sameCamera(payload, camera));
        const camera = existing
            ? await GoHomeEdge.updateCamera(existing.id, payload)
            : await GoHomeEdge.createCamera(payload);
        state.selectedCameraId = camera.id;
        await disableOtherLocalCameras(camera.id);
        await loadCameras();
        return camera;
    }

    function renderPreview(snapshot, result) {
        const image = $("connectionPreviewImage");
        const empty = $("connectionPreviewEmpty");
        if (snapshot?.image_url) {
            image.src = `${GoHomeEdge.edgeUrl(snapshot.image_url)}?t=${Date.now()}`;
            image.classList.remove("hidden");
            empty.classList.add("hidden");
        }
        setText("connectionResultTitle", "画面已接入");
        setText("connectionResultText", `${result.width}x${result.height} · ${result.analysis?.detector_backend || "basic"} · 人数 ${snapshot.person_count ?? "-"}`);
        setText("edgeLastTest", "通过");
    }

    function renderCameras() {
        const list = $("cameraList");
        const networkCameras = state.cameras.filter((camera) => !isLocalCamera(camera));
        $("edgeCameraCount").textContent = String(networkCameras.length);
        $("cameraListBadge").textContent = networkCameras.length ? `${networkCameras.length} 路` : "未接入";

        const active = preferredCamera(state.cameras);
        setText("edgeActiveRoom", active?.room || active?.name || "-");

        if (!state.cameras.length) {
            list.innerHTML = `
                <div class="app-soft-card bg-white p-5 text-center">
                    <span class="material-symbols-outlined text-primary text-[30px]">add_circle</span>
                    <p class="font-display text-[17px] font-bold text-on-surface mt-2">还没有摄像头</p>
                    <p class="font-sans text-[12px] text-on-surface-variant mt-1">先填写上面的信息并测试画面。</p>
                </div>
            `;
            return;
        }

        list.innerHTML = state.cameras.map((camera) => {
            const isActive = camera.id === state.selectedCameraId;
            const badge = camera.enabled ? statusLabel(camera.status) : "已禁用";
            const color = camera.enabled && camera.status === "online" ? "text-[#2d7d5c] bg-[#edf6ee]" : "text-[#c87b2a] bg-[#fff4e8]";
            return `
                <article class="app-soft-card bg-white p-4 ${isActive ? "border-primary/30" : ""}">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <p class="font-display text-[16px] font-bold text-on-surface">${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置")}</p>
                            <p class="font-sans text-[12px] text-on-surface-variant mt-1 break-all">${escapeHtml(camera.stream_url)}</p>
                        </div>
                        <span class="px-2.5 py-1 rounded-full ${color} text-[10px] font-bold shrink-0">${badge}</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-3">
                        <button class="h-10 rounded-2xl bg-[#f4f6fb] text-on-surface font-sans text-[12px] font-bold" data-action="load" data-id="${camera.id}">填入表单</button>
                        <button class="h-10 rounded-2xl bg-primary text-white font-sans text-[12px] font-bold" data-action="test" data-id="${camera.id}">测试</button>
                    </div>
                </article>
            `;
        }).join("");
    }

    async function loadCameras() {
        state.cameras = await GoHomeEdge.cameras();
        const preferred = preferredCamera(state.cameras);
        state.selectedCameraId = state.selectedCameraId || preferred?.id || null;
        renderCameras();
        if (preferred) {
            fillFormFromCamera(preferred);
        }
    }

    async function testCamera(cameraId, button) {
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
                const camera = await saveCamera(payloadFromForm());
                const result = await testCamera(camera.id, $("testCameraButton"));
                renderPreview(result.snapshot, result);
            } catch (error) {
                setText("connectionResultTitle", "保存或测试失败");
                setText("connectionResultText", error.message || "请检查摄像头 IP、账号、密码和同一局域网连接。");
                setText("edgeLastTest", "失败");
            } finally {
                setBusy(button, false);
            }
        });

        $("testCameraButton").addEventListener("click", async (event) => {
            try {
                const camera = await saveCamera(payloadFromForm());
                await testCamera(camera.id, event.currentTarget);
            } catch (error) {
                setText("connectionResultTitle", "测试失败");
                setText("connectionResultText", error.message || "请检查摄像头配置。");
                setText("edgeLastTest", "失败");
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
            }
            if (button.dataset.action === "test") {
                try {
                    await testCamera(cameraId, button);
                } catch (error) {
                    setText("connectionResultTitle", "测试失败");
                    setText("connectionResultText", error.message || "请检查摄像头配置。");
                    setText("edgeLastTest", "失败");
                }
            }
        });
    });
})();
