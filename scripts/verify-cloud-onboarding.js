#!/usr/bin/env node
"use strict";

const assert = require("assert");

const baseUrl = String(process.env.GOHOME_APP_BASE_URL || process.argv[2] || "http://127.0.0.1:8788").replace(/\/$/, "");
const opsToken = String(process.env.GOHOME_OPS_TOKEN || "").trim();
const stamp = `${Date.now()}`.slice(-8);
const ownerPhone = `199${stamp}`;
const memberPhone = `198${stamp}`;
const deviceId = `verify-onboarding-${stamp}`;
const results = [];

function record(name, detail = "") {
    results.push({ name, detail });
}

async function request(pathname, options = {}) {
    const response = await fetch(`${baseUrl}${pathname}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
        },
    });
    const text = await response.text();
    let payload = null;
    try {
        payload = text ? JSON.parse(text) : null;
    } catch (_error) {
        payload = text;
    }
    return { response, payload, text };
}

async function json(pathname, options = {}) {
    const result = await request(pathname, options);
    if (!result.response.ok) {
        throw new Error(`${options.method || "GET"} ${pathname}: ${result.response.status} ${result.text}`);
    }
    return result.payload;
}

async function cleanup() {
    const query = opsToken ? `?ops_token=${encodeURIComponent(opsToken)}` : "";
    const result = await request(`/api/v1/internal/verify-data/cleanup${query}`, {
        method: "POST",
        body: JSON.stringify({ dry_run: false }),
    });
    if (!result.response.ok) {
        throw new Error(`cleanup failed: ${result.response.status} ${result.text}`);
    }
    record("清理测试数据", JSON.stringify(result.payload.deleted || {}));
}

async function main() {
    try {
        const health = await json("/health");
        assert.equal(health.ok, true);
        record("云端服务", `store=${health.store}`);

        const owner = await json("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ phone: ownerPhone, code: "000000", display_name: "流程自检创建者" }),
        });
        assert.ok(owner.token);
        record("创建者注册", ownerPhone);

        const emptyFamilies = await json("/api/families/mine", { token: owner.token });
        const emptyCameras = await json("/api/app/cameras", { token: owner.token });
        assert.equal(emptyFamilies.length, 0);
        assert.equal(emptyCameras.length, 0);
        record("新账号隔离", "无旧家庭、盒子和摄像头");

        const family = await json("/api/families", {
            method: "POST",
            token: owner.token,
            body: JSON.stringify({ name: `流程自检-${stamp}` }),
        });
        assert.ok(family.id);
        record("创建家庭", String(family.id));

        const profile = await json(`/api/v1/families/${family.id}/elders/elder_primary/profile`, {
            method: "PUT",
            token: owner.token,
            body: JSON.stringify({
                display_name: "测试妈妈",
                relationship: "母亲",
                city: "上海",
                district: "浦东新区",
                mobile_phone: "13900000000",
                home_phone: "021-00000000",
            }),
        });
        assert.equal(profile.display_name, "测试妈妈");
        record("老人资料", "称呼、地区和电话已保存");

        const ownerRules = await json(`/api/rules?family_id=${family.id}`, { token: owner.token });
        const ruleKeys = [
            "offline_enabled",
            "black_screen_enabled",
            "no_motion_enabled",
            "person_detection_enabled",
            "fall_detection_enabled",
            "activity_detection_enabled",
            "fire_detection_enabled",
            "notification_enabled",
        ];
        assert.equal(ownerRules.can_edit, true);
        assert.ok(ruleKeys.every((key) => ownerRules[key] === true));
        record("家庭默认规则", "八项全开，创建者可修改");

        const member = await json("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ phone: memberPhone, code: "000000", display_name: "流程自检成员" }),
        });
        await json("/api/families/join", {
            method: "POST",
            token: member.token,
            body: JSON.stringify({ code: family.join_code }),
        });
        const memberRules = await json(`/api/rules?family_id=${family.id}`, { token: member.token });
        assert.equal(memberRules.can_edit, false);
        const blockedUpdate = await request(`/api/rules?family_id=${family.id}`, {
            method: "PUT",
            token: member.token,
            body: JSON.stringify({ fall_detection_enabled: false }),
        });
        assert.equal(blockedUpdate.response.status, 403);
        record("成员权限", "可查看，修改返回 403");

        const bindingCode = await json("/api/device/binding-codes", {
            method: "POST",
            token: owner.token,
            body: JSON.stringify({ family_id: family.id, expires_in_minutes: 10 }),
        });
        const exchanged = await json("/api/device/token/exchange", {
            method: "POST",
            token: owner.token,
            body: JSON.stringify({ code: bindingCode.code, device_id: deviceId, device_name: "流程自检盒子" }),
        });
        assert.ok(exchanged.device_token);
        record("绑定盒子", deviceId);

        await json("/api/v1/device/heartbeat", {
            method: "POST",
            token: exchanged.device_token,
            body: JSON.stringify({ device_id: deviceId, name: "流程自检盒子", status: "online" }),
        });
        const camera = await json("/api/cameras", {
            method: "POST",
            token: owner.token,
            body: JSON.stringify({
                family_id: family.id,
                device_id: deviceId,
                name: "流程自检摄像头",
                room: "客厅",
                stream_url: "demo:onboarding",
                enabled: true,
            }),
        });
        const config = await json("/api/v1/device/config", { token: exchanged.device_token });
        assert.equal(config.cameras.length, 1);
        assert.equal(String(config.cameras[0].id), String(camera.id));
        assert.ok(ruleKeys.every((key) => config.rules[key] === true));
        record("盒子配置下发", "摄像头和家庭规则正确");

        await json("/api/v1/device/sync", {
            method: "POST",
            token: exchanged.device_token,
            body: JSON.stringify({
                device_id: deviceId,
                config_version: config.config_version,
                worker_running: true,
                applied_rule_version: config.rules_version,
                status: { status: "online", sync_status: "healthy" },
                cameras: [{
                    camera_id: camera.id,
                    local_camera_id: 1,
                    status: "online",
                    sync_status: "synced",
                    enabled: true,
                    last_error: "",
                }],
            }),
        });
        let appCameras = [];
        for (let attempt = 0; attempt < 10; attempt += 1) {
            appCameras = await json("/api/app/cameras", { token: owner.token });
            if (appCameras[0]?.status === "online" && appCameras[0]?.sync_status === "synced") break;
            await new Promise((resolve) => setTimeout(resolve, 250));
        }
        assert.equal(appCameras.length, 1);
        assert.equal(appCameras[0].status, "online", JSON.stringify(appCameras[0]));
        assert.equal(appCameras[0].sync_status, "synced", JSON.stringify(appCameras[0]));
        record("App 摄像头状态", "online / synced");

        const changedRules = await json(`/api/rules?family_id=${family.id}`, {
            method: "PUT",
            token: owner.token,
            body: JSON.stringify({ activity_detection_enabled: false }),
        });
        assert.equal(changedRules.activity_detection_enabled, false);
        const changedConfig = await json("/api/v1/device/config", { token: exchanged.device_token });
        assert.equal(changedConfig.rules.activity_detection_enabled, false);
        assert.equal(changedConfig.rules.fire_detection_enabled, true);
        await json(`/api/rules?family_id=${family.id}`, {
            method: "PUT",
            token: owner.token,
            body: JSON.stringify({ activity_detection_enabled: true }),
        });
        record("家庭规则隔离", "创建者修改后仅下发给本家庭盒子");

        const bindings = await json(`/api/device-bindings?family_id=${family.id}`, { token: owner.token });
        assert.equal(bindings.length, 1);
        await json(`/api/device-bindings/${bindings[0].id}`, { method: "DELETE", token: owner.token });
        const camerasAfterUnbind = await json("/api/app/cameras", { token: owner.token });
        assert.equal(camerasAfterUnbind.length, 0);
        const revokedDeviceAccess = await request("/api/v1/device/config", { token: exchanged.device_token });
        assert.equal(revokedDeviceAccess.response.status, 401);
        record("解绑清理", "盒子和摄像头关系已移除，旧设备 token 已撤销");
    } finally {
        await cleanup();
    }

    for (const item of results) {
        console.log(`OK ${item.name}${item.detail ? ` - ${item.detail}` : ""}`);
    }
    console.log(`\nSummary: ${results.length} passed, 0 failed`);
}

main().catch((error) => {
    console.error(`FAIL ${error.stack || error.message}`);
    process.exit(1);
});
