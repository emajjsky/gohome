(function () {
    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function statusClass(capability) {
        return capability.configured ? "good" : "warn";
    }

    function statusLabel(capability) {
        return capability.configured ? "已配置" : "待配置";
    }

    function envList(keys = []) {
        return keys.map((key) => `<code>${escapeHtml(key)}</code>`).join("");
    }

    function promptPreview(prompt) {
        const raw = String(prompt || "").trim();
        if (!raw) return "-";
        return raw.length > 220 ? `${raw.slice(0, 220)}...` : raw;
    }

    function renderCapability(capability) {
        const env = capability.env_keys || {};
        return `
            <article class="ops-capability" data-capability-id="${escapeHtml(capability.capability_id)}">
                <div class="ops-capability-head">
                    <div class="min-w-0">
                        <p class="ops-capability-id">${escapeHtml(capability.capability_id)}</p>
                        <h3>${escapeHtml(capability.name)}</h3>
                        <p class="ops-capability-desc">${escapeHtml(capability.output_contract || "")}</p>
                    </div>
                    <span class="ops-badge ${statusClass(capability)}">${statusLabel(capability)}</span>
                </div>

                <div class="ops-field-grid">
                    <div class="ops-read-field">
                        <span>Base URL</span>
                        <strong>${capability.base_url_set ? "已设置" : "未配置"}</strong>
                    </div>
                    <div class="ops-read-field">
                        <span>API Key</span>
                        <strong>${capability.api_key_set ? "已设置" : "未配置"}</strong>
                    </div>
                    <div class="ops-read-field">
                        <span>Model</span>
                        <strong>${escapeHtml(capability.model || "未配置")}</strong>
                    </div>
                    <div class="ops-read-field">
                        <span>用途</span>
                        <strong>${escapeHtml(capability.purpose_label || capability.scope || "-")}</strong>
                    </div>
                </div>

                <div class="ops-prompt-block">
                    <span>默认 Prompt</span>
                    <pre>${escapeHtml(promptPreview(capability.prompt))}</pre>
                </div>

                <div class="ops-env-block">
                    <span>平台方配置环境变量</span>
                    <div class="ops-env-row"><em>base_url</em>${envList(env.base_url)}</div>
                    <div class="ops-env-row"><em>api_key</em>${envList(env.api_key)}</div>
                    <div class="ops-env-row"><em>model</em>${envList(env.model)}</div>
                    <div class="ops-env-row"><em>prompt</em>${envList(env.prompt)}</div>
                </div>
            </article>
        `;
    }

    function renderConfig(config) {
        const capabilities = Array.isArray(config.model_capabilities) ? config.model_capabilities : [];
        const configured = capabilities.filter((item) => item.configured).length;
        setText("opsServiceStatus", config.ok ? "在线" : "异常");
        setText("opsStoreKind", config.store || "-");
        setText("opsCapabilitySummary", `${configured}/${capabilities.length} 已配置`);
        const policy = config.secret_policy || {};
        setText("opsSecretPolicy", `本地 ${policy.local || "-"}；云端 ${policy.cloud || "-"}；数据库 ${policy.database || "-"}；用户可配置：${policy.user_configurable ? "是" : "否"}`);

        const list = $("opsCapabilityList");
        if (!list) return;
        list.innerHTML = capabilities.length
            ? capabilities.map(renderCapability).join("")
            : `<div class="ops-empty">还没有模型能力配置。</div>`;
    }

    async function loadConfig() {
        if (!window.GoHomeEdge) return;
        const config = await GoHomeEdge.v1OpsServiceConfig();
        renderConfig(config);
    }

    async function bootstrap() {
        if (!window.GoHomeEdge) return;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            await loadConfig();
        } catch (error) {
            setText("opsServiceStatus", "未连接");
            setText("opsCapabilitySummary", "-");
            setText("opsSecretPolicy", error.message || "后台服务不可用");
            const list = $("opsCapabilityList");
            if (list) list.innerHTML = `<div class="ops-empty">${escapeHtml(error.message || "后台服务不可用")}</div>`;
        }
    }

    $("opsRefreshBtn")?.addEventListener("click", () => {
        loadConfig().catch((error) => {
            setText("opsServiceStatus", "刷新失败");
            setText("opsSecretPolicy", error.message || "刷新失败");
        });
    });

    document.addEventListener("DOMContentLoaded", bootstrap);
})();
