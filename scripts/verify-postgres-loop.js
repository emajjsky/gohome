#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");

const APP_TOKEN = process.env.GOHOME_APP_TOKEN || "gohome-local-app-token";
const DEVICE_TOKEN = process.env.GOHOME_DEVICE_API_TOKEN || "gohome-local-device-token";

function parseArgs(argv) {
    const args = {
        databaseUrl: process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL || "",
        allowNonEmpty: false,
        skipMigrations: false,
    };
    for (let index = 0; index < argv.length; index += 1) {
        const arg = argv[index];
        if (arg === "--database-url") args.databaseUrl = argv[++index] || "";
        else if (arg === "--allow-non-empty") args.allowNonEmpty = true;
        else if (arg === "--skip-migrations") args.skipMigrations = true;
        else if (arg === "--help" || arg === "-h") args.help = true;
        else throw new Error(`unknown argument: ${arg}`);
    }
    return args;
}

function printHelp() {
    console.log([
        "Usage: GOHOME_DATABASE_URL=postgres://... npm run verify:postgres-loop",
        "",
        "Runs migrations, starts local-app-server with PostgresStore, and verifies",
        "the same app-facing loop against a real PostgreSQL database.",
        "",
        "Options:",
        "  --database-url <url>  PostgreSQL connection URL",
        "  --allow-non-empty     Allow verification against a database with existing rows",
        "  --skip-migrations     Do not run scripts/apply-postgres-migrations.js first",
    ].join("\n"));
}

function listen(server) {
    return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();
            resolve(`http://127.0.0.1:${address.port}`);
        });
    });
}

async function requestJson(baseUrl, pathName, options = {}) {
    const response = await fetch(`${baseUrl}${pathName}`, {
        ...options,
        headers: {
            Accept: "application/json",
            Authorization: `Bearer ${APP_TOKEN}`,
            ...(options.headers || {}),
        },
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) {
        throw new Error(`${pathName} -> ${response.status} ${text}`);
    }
    return payload;
}

function runMigrations(databaseUrl) {
    const migrationScript = path.resolve(__dirname, "apply-postgres-migrations.js");
    const result = spawnSync(process.execPath, [migrationScript, "--database-url", databaseUrl], {
        cwd: path.resolve(__dirname, ".."),
        env: process.env,
        encoding: "utf8",
    });
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    if (result.status !== 0) {
        throw new Error(`postgres migrations failed with exit code ${result.status}`);
    }
}

async function rowCounts(databaseUrl) {
    const { Client } = require("pg");
    const { TABLE_ORDER } = require("../local-app-server/postgres-store");
    const client = new Client({
        connectionString: databaseUrl,
        ssl: process.env.GOHOME_DATABASE_SSL === "1" || process.env.GOHOME_DATABASE_SSL === "true"
            ? { rejectUnauthorized: false }
            : undefined,
    });
    await client.connect();
    try {
        const counts = {};
        for (const table of TABLE_ORDER) {
            const result = await client.query(`select count(*)::int as count from ${table}`);
            counts[table] = Number(result.rows[0]?.count || 0);
        }
        return counts;
    } finally {
        await client.end();
    }
}

function totalRows(counts) {
    return Object.values(counts).reduce((sum, count) => sum + Number(count || 0), 0);
}

async function main() {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
        printHelp();
        return;
    }
    if (!args.databaseUrl) {
        throw new Error("GOHOME_DATABASE_URL or --database-url is required for Postgres loop verification");
    }

    if (!args.skipMigrations) {
        runMigrations(args.databaseUrl);
    }

    const beforeCounts = await rowCounts(args.databaseUrl);
    const beforeTotal = totalRows(beforeCounts);
    if (beforeTotal > 0 && !args.allowNonEmpty) {
        throw new Error(`database is not empty (${beforeTotal} app rows). Use a fresh database or pass --allow-non-empty for read verification.`);
    }

    const { createLocalAppServerAsync } = require("../local-app-server/server");
    const app = await createLocalAppServerAsync({
        rootDir: path.resolve(__dirname, ".."),
        databaseUrl: args.databaseUrl,
        storeKind: "postgres",
        appToken: APP_TOKEN,
        deviceToken: DEVICE_TOKEN,
    });
    const baseUrl = await listen(app.server);

    try {
        const health = await requestJson(baseUrl, "/health");
        if (health.store !== "postgres") {
            throw new Error(`expected postgres store, got ${health.store || "unknown"}`);
        }

        const user = await requestJson(baseUrl, "/api/users/me");
        const families = await requestJson(baseUrl, "/api/families/mine");
        const family = Array.isArray(families) ? families[0] : null;
        const cameras = await requestJson(baseUrl, "/api/app/cameras");
        const summary = await requestJson(baseUrl, "/api/app/summary/today");
        const providers = await requestJson(baseUrl, "/api/v1/model-providers");

        if (!user?.id) throw new Error("missing current user from postgres-backed app server");
        if (!family?.id) throw new Error("missing family from postgres-backed app server");
        if (!Array.isArray(cameras)) throw new Error("camera list is not an array");
        if (!summary || typeof summary !== "object") throw new Error("summary payload is invalid");
        if (!Array.isArray(providers)) throw new Error("model provider list is not an array");

        const afterCounts = await rowCounts(args.databaseUrl);
        console.log(JSON.stringify({
            ok: true,
            base_url: baseUrl,
            store: health.store,
            user: user.display_name || user.email || user.id,
            family: family.name || family.id,
            cameras: cameras.length,
            open_events: Number(summary.open_events || 0),
            rows_before: beforeTotal,
            rows_after: totalRows(afterCounts),
        }, null, 2));
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        if (app.store && typeof app.store.close === "function") {
            await app.store.close();
        }
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
