#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
    const args = {
        databaseUrl: process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL || "",
        migrationsDir: path.resolve("local-app-server/migrations"),
        dryRun: false,
    };
    for (let index = 0; index < argv.length; index += 1) {
        const arg = argv[index];
        if (arg === "--database-url") args.databaseUrl = argv[++index] || "";
        else if (arg === "--migrations-dir") args.migrationsDir = path.resolve(argv[++index] || "");
        else if (arg === "--dry-run") args.dryRun = true;
        else if (arg === "--help" || arg === "-h") args.help = true;
        else throw new Error(`unknown argument: ${arg}`);
    }
    return args;
}

function printHelp() {
    console.log([
        "Usage: GOHOME_DATABASE_URL=postgres://... npm run db:migrate",
        "",
        "Options:",
        "  --database-url <url>     PostgreSQL connection URL",
        "  --migrations-dir <path>  Migration directory, defaults to local-app-server/migrations",
        "  --dry-run                List pending migration files without connecting",
    ].join("\n"));
}

function sha256(value) {
    return crypto.createHash("sha256").update(value).digest("hex");
}

function migrationFiles(migrationsDir) {
    return fs.readdirSync(migrationsDir)
        .filter((file) => /^\d+_.+\.sql$/.test(file))
        .sort()
        .map((file) => path.join(migrationsDir, file));
}

function postgresSslConfig() {
    return process.env.GOHOME_DATABASE_SSL === "1" || process.env.GOHOME_DATABASE_SSL === "true"
        ? { rejectUnauthorized: false }
        : undefined;
}

async function ensureMigrationTable(client) {
    await client.query([
        "create table if not exists schema_migrations (",
        "  version text primary key,",
        "  checksum text not null,",
        "  applied_at timestamptz not null default now()",
        ");",
    ].join("\n"));
}

async function appliedChecksum(client, version) {
    const result = await client.query(
        "select checksum from schema_migrations where version = $1",
        [version],
    );
    return result.rows[0]?.checksum || "";
}

async function recordMigration(client, version, checksum) {
    await client.query(
        "insert into schema_migrations (version, checksum) values ($1, $2) on conflict (version) do nothing",
        [version, checksum],
    );
}

async function applyMigration(client, filePath) {
    const version = path.basename(filePath);
    const sql = fs.readFileSync(filePath, "utf8");
    const checksum = sha256(sql);
    const existingChecksum = await appliedChecksum(client, version);
    if (existingChecksum) {
        if (existingChecksum !== checksum) {
            throw new Error(`migration checksum changed after apply: ${version}`);
        }
        return { version, status: "skipped" };
    }
    await client.query(sql);
    await recordMigration(client, version, checksum);
    return { version, status: "applied" };
}

async function main() {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
        printHelp();
        return;
    }
    const files = migrationFiles(args.migrationsDir);
    if (args.dryRun) {
        console.log(JSON.stringify({
            ok: true,
            migrations_dir: args.migrationsDir,
            migrations: files.map((file) => path.basename(file)),
        }, null, 2));
        return;
    }
    if (!args.databaseUrl) {
        throw new Error("GOHOME_DATABASE_URL or --database-url is required");
    }
    const { Client } = require("pg");
    const client = new Client({
        connectionString: args.databaseUrl,
        ssl: postgresSslConfig(),
    });
    await client.connect();
    try {
        await ensureMigrationTable(client);
        const results = [];
        for (const file of files) {
            results.push(await applyMigration(client, file));
        }
        console.log(JSON.stringify({
            ok: true,
            migrations_dir: args.migrationsDir,
            results,
        }, null, 2));
    } finally {
        await client.end();
    }
}

if (require.main === module) {
    main().catch((error) => {
        console.error(error.message || error);
        process.exit(1);
    });
}
