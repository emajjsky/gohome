(function () {
    const SNAPSHOT_ROOT = "gohome.pageSnapshot.";
    const SNAPSHOT_PREFIX = `${SNAPSHOT_ROOT}v5.`;
    const AUTH_TOKEN_KEY = "gohome.authToken";
    const MAX_SNAPSHOT_AGE_MS = 24 * 60 * 60 * 1000;
    const MAX_SNAPSHOT_BYTES = 600 * 1024;
    const CAPTURE_DELAY_MS = 120;
    const REFRESH_DELAY_MS = 180;
    const PAGE_NAMES = new Set([
        "index.html",
        "monitor.html",
        "events.html",
        "companionship.html",
        "privacy.html",
    ]);
    const DYNAMIC_BODY_CLASSES = ["gohome-setup-mode"];
    let restored = false;
    let ready = false;
    let captureTimer = null;
    let refreshTimer = null;
    let suppressCapture = false;
    let bootSnapshot = null;

    function currentPage() {
        return window.location.pathname.split("/").pop() || "index.html";
    }

    function cookieValue(name) {
        const prefix = `${name}=`;
        const item = String(document.cookie || "")
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith(prefix));
        if (!item) return "";
        try {
            return decodeURIComponent(item.slice(prefix.length));
        } catch (_error) {
            return item.slice(prefix.length);
        }
    }

    function accountScope() {
        const params = new URLSearchParams(window.location.search);
        const launchToken = params.get("auth_token") || params.get("authToken") || "";
        const token = launchToken || localStorage.getItem(AUTH_TOKEN_KEY) || cookieValue("gohome_app_session") || "guest";
        return token === "guest" ? token : token.slice(-16);
    }

    function snapshotKey() {
        return `${SNAPSHOT_PREFIX}${accountScope()}.${currentPage()}`;
    }

    function reveal() {
        document.documentElement.classList.remove("gohome-state-pending");
        document.documentElement.classList.remove("gohome-state-restorable");
    }

    function readSnapshot() {
        try {
            const raw = localStorage.getItem(snapshotKey());
            if (!raw) return null;
            const snapshot = JSON.parse(raw);
            if (!snapshot?.main_html || Date.now() - Number(snapshot.captured_at || 0) > MAX_SNAPSHOT_AGE_MS) {
                localStorage.removeItem(snapshotKey());
                return null;
            }
            return snapshot;
        } catch (_error) {
            localStorage.removeItem(snapshotKey());
            return null;
        }
    }

    function cleanupLegacySnapshots() {
        for (let index = localStorage.length - 1; index >= 0; index -= 1) {
            const key = localStorage.key(index) || "";
            if (key.startsWith(SNAPSHOT_ROOT) && !key.startsWith(SNAPSHOT_PREFIX)) {
                localStorage.removeItem(key);
            }
        }
    }

    function isTemporaryImageSource(value) {
        const source = String(value || "");
        return /stream\.mjpg|access_token=/i.test(source);
    }

    function sanitizedMainHtml(main) {
        const clone = main.cloneNode(true);
        clone.querySelectorAll("script, dialog, [role='dialog'], .gohome-toast, [data-transient='true']")
            .forEach((node) => node.remove());
        clone.querySelectorAll("input, textarea, select").forEach((field) => {
            field.removeAttribute("value");
            field.removeAttribute("checked");
            field.querySelectorAll?.("option[selected]").forEach((option) => option.removeAttribute("selected"));
            if (field.tagName === "TEXTAREA") field.textContent = "";
        });
        clone.querySelectorAll("img").forEach((image) => {
            const source = image.getAttribute("src") || "";
            if (!isTemporaryImageSource(source)) return;
            image.removeAttribute("src");
            image.removeAttribute("srcset");
            image.classList.remove("opacity-0");
        });
        return clone.innerHTML;
    }

    function removeExpiredPlaybackImages() {
        document.querySelectorAll("main img[src*='playback_ticket=']").forEach((image) => {
            const source = image.getAttribute("src") || "";
            let issuedAt = 0;
            try {
                issuedAt = Number(new URL(source, window.location.href).searchParams.get("t") || 0);
            } catch (_error) {
                issuedAt = 0;
            }
            if (issuedAt > 0 && Date.now() - issuedAt < 90_000) return;
            image.removeAttribute("src");
            if (image.id === "edgeHomeCareImage" || image.id === "companionshipCareImage") {
                image.classList.add("hidden");
                const fallbackId = image.id === "edgeHomeCareImage"
                    ? "edgeHomeCareImageFallback"
                    : "companionshipCareImageFallback";
                document.getElementById(fallbackId)?.classList.remove("hidden");
            }
        });
    }

    function captureNow() {
        if (suppressCapture || !ready || !PAGE_NAMES.has(currentPage())) return false;
        const main = document.querySelector("main");
        if (!main) return false;
        try {
            const snapshot = {
                captured_at: Date.now(),
                main_html: sanitizedMainHtml(main),
                scroll_y: Math.max(0, Math.round(window.scrollY || 0)),
                body_classes: DYNAMIC_BODY_CLASSES.filter((name) => document.body?.classList.contains(name)),
            };
            const serialized = JSON.stringify(snapshot);
            if (serialized.length > MAX_SNAPSHOT_BYTES) return false;
            localStorage.setItem(snapshotKey(), serialized);
            return true;
        } catch (_error) {
            return false;
        }
    }

    function scheduleCapture() {
        if (captureTimer) window.clearTimeout(captureTimer);
        captureTimer = window.setTimeout(() => {
            captureTimer = null;
            captureNow();
        }, CAPTURE_DELAY_MS);
    }

    function restore(snapshot = readSnapshot()) {
        if (!PAGE_NAMES.has(currentPage())) {
            reveal();
            return false;
        }
        const main = document.querySelector("main");
        if (!snapshot || !main) return false;
        main.innerHTML = snapshot.main_html;
        removeExpiredPlaybackImages();
        DYNAMIC_BODY_CLASSES.forEach((name) => {
            document.body.classList.toggle(name, snapshot.body_classes?.includes(name) === true);
        });
        restored = true;
        ready = true;
        reveal();
        window.requestAnimationFrame(() => window.scrollTo(0, Number(snapshot.scroll_y || 0)));
        return true;
    }

    function markPageReady() {
        ready = true;
        reveal();
        scheduleCapture();
    }

    function clearAll(options = {}) {
        suppressCapture = options.suppressCapture !== false;
        for (let index = localStorage.length - 1; index >= 0; index -= 1) {
            const key = localStorage.key(index) || "";
            if (key.startsWith(SNAPSHOT_ROOT)) localStorage.removeItem(key);
        }
        restored = false;
        ready = false;
    }

    function refreshCurrentPage() {
        if (document.hidden || typeof window.GoHomeRefreshPage !== "function") return;
        if (refreshTimer) window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(() => {
            refreshTimer = null;
            window.GoHomeRefreshPage();
        }, REFRESH_DELAY_MS);
    }

    cleanupLegacySnapshots();
    bootSnapshot = readSnapshot();
    if (bootSnapshot) document.documentElement.classList.add("gohome-state-restorable");
    const style = document.createElement("style");
    style.id = "gohome-state-boot-style";
    style.textContent = `
        html.gohome-state-restorable body > main { visibility: hidden !important; }
    `;
    document.head.append(style);

    document.addEventListener("DOMContentLoaded", () => {
        restore(bootSnapshot);
        reveal();
    });
    window.addEventListener("gohome:data-updated", refreshCurrentPage);
    window.addEventListener("pagehide", captureNow);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) captureNow();
    });

    window.GoHomeAppStore = {
        markPageReady,
        scheduleCapture,
        clearAll,
        hasRestoredSnapshot: () => restored,
        hasVisibleState: () => restored || ready,
    };
})();
