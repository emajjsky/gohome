#!/usr/bin/env node
"use strict";

const DEFAULT_BASE_URL = "http://127.0.0.1:8788";

const args = new Set(process.argv.slice(2));
const apply = args.has("--apply");
const baseUrl = String(process.env.GOHOME_APP_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
const opsToken = String(process.env.GOHOME_OPS_TOKEN || "").trim();

function endpoint() {
    const url = new URL(`${baseUrl}/api/v1/internal/verify-data/cleanup`);
    if (opsToken) url.searchParams.set("ops_token", opsToken);
    return url.toString();
}

async function main() {
    const response = await fetch(endpoint(), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ dry_run: !apply }),
    });
    const text = await response.text();
    let payload = null;
    try {
        payload = text ? JSON.parse(text) : null;
    } catch (_error) {
        payload = { detail: text };
    }
    if (!response.ok) {
        throw new Error(payload?.detail || `cleanup failed: HTTP ${response.status}`);
    }
    const deleted = payload?.deleted || {};
    const targets = payload?.targets || {};
    const total = Object.values(deleted).reduce((sum, value) => sum + Number(value || 0), 0);
    console.log(`${payload.dry_run ? "DRY RUN" : "CLEANED"} verify data at ${baseUrl}`);
    console.log(`Targets: ${targets.users?.length || 0} user(s), ${targets.families?.length || 0} family/families`);
    for (const [key, value] of Object.entries(deleted)) {
        if (Number(value || 0) > 0) console.log(`- ${key}: ${value}`);
    }
    console.log(`Total removable records: ${total}`);
    if (payload.dry_run) {
        console.log("Run with --apply to delete these records.");
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
