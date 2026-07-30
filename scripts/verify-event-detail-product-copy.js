const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");


function element() {
    return {
        textContent: "",
        innerHTML: "",
        href: "",
        src: "",
        disabled: false,
        classList: {
            add() {},
            remove() {},
            toggle() {},
        },
        addEventListener() {},
    };
}


async function main() {
    const elements = new Map();
    let ready = null;
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, element());
            return elements.get(id);
        },
        addEventListener(name, callback) {
            if (name === "DOMContentLoaded") ready = callback;
        },
    };
    const event = {
        id: 200,
        type: "fall_candidate",
        level: "critical",
        room: "客厅",
        camera_name: "客厅摄像头",
        occurred_at: "2026-07-21T04:02:15.458Z",
        acknowledged: false,
        evidence_media: [],
        payload: {
            rule: {
                label: "跌倒应急报警",
                reason: "同一人体先出现站坐状态，随后快速下降。",
                observed: {
                    fall_score: 0.88,
                    pose_fall_score: 0.88,
                    target: { posture: "bending" },
                    transition: { confirmed: true },
                },
                threshold: {
                    fall_score: 0.5,
                    confirm_frames: 2,
                },
            },
            evaluation: {
                state: {
                    fall_state: "confirmed",
                    fall_target: { posture: "bending" },
                },
            },
            verification: {
                status: "rejected",
                result: {
                    reason: "画面中人物正弯腰取物，未见跌倒或倒地。",
                },
            },
            incident: { status: "rejected", transitions: [] },
        },
    };
    const GoHomeEdge = {
        async connect() {},
        async appEvent() { return event; },
        pageHref(value) { return value; },
        loginHref(value) { return value; },
        currentPagePath() { return "/event_detail.html"; },
        clearAuthToken() {},
        fmtTime() { return "12:02"; },
        fmtDateTime() { return "7月21日 12:02"; },
        eventLabel() { return "疑似跌倒"; },
        async v1VideoMediaPlaybackUrl(value) { return value; },
        async v1VideoAssetPlaybackUrl(value) { return value; },
    };
    const window = {
        document,
        GoHomeEdge,
        location: {
            search: "?eventId=200&camera_id=2&app=1",
            href: "",
        },
    };
    const context = vm.createContext({
        window,
        document,
        GoHomeEdge,
        URLSearchParams,
        console,
        setTimeout,
        clearTimeout,
    });
    const source = fs.readFileSync("assets/scripts/event-detail-live.js", "utf8");
    vm.runInContext(source, context, { filename: "event-detail-live.js" });
    assert.equal(typeof ready, "function");
    ready();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const detail = document.getElementById("edgeDetailFactSub").textContent;
    assert.match(detail, /未见跌倒或倒地/);
    assert.doesNotMatch(detail, /fall_score|pose_fall_score|confirm_frames|\[object Object\]|规则阈值|评估状态/);
    assert.doesNotMatch(detail, /[。！？.!?]{2,}/);
    assert.ok(detail.length <= 180, `event detail copy is too long: ${detail.length}`);
    console.log(JSON.stringify({ ok: true, detail }, null, 2));
}


main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
