from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import sys
import tempfile


EDGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDGE_ROOT.parent
APP_DIR = EDGE_ROOT / "app"
CLOUD_SERVER = REPO_ROOT / "local-app-server" / "server.js"
CLOUD_APNS_PROVIDER = REPO_ROOT / "local-app-server" / "apns-provider.js"


def decorated_routes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            route = decorator.args[0]
            if isinstance(route, ast.Constant) and isinstance(route.value, str):
                routes.add(route.value)
    return routes


def assigned_settings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                names.add(target.attr)
    return names


def verify_legacy_database_migration() -> None:
    sys.path.insert(0, str(EDGE_ROOT))
    from app.storage import Storage

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "edge.db"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE rules (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    capture_interval_seconds INTEGER NOT NULL,
                    motion_threshold REAL NOT NULL DEFAULT 0.015,
                    black_brightness_threshold REAL NOT NULL DEFAULT 18,
                    black_contrast_threshold REAL NOT NULL DEFAULT 4,
                    yolo_confidence REAL NOT NULL DEFAULT 0.20,
                    no_motion_seconds INTEGER NOT NULL,
                    black_screen_enabled INTEGER NOT NULL,
                    no_motion_enabled INTEGER NOT NULL,
                    person_detection_enabled INTEGER NOT NULL,
                    fall_detection_enabled INTEGER NOT NULL,
                    fall_score_threshold REAL NOT NULL DEFAULT 0.50,
                    fall_confirm_frames INTEGER NOT NULL DEFAULT 2,
                    fall_confirm_seconds INTEGER NOT NULL DEFAULT 4,
                    fall_recover_frames INTEGER NOT NULL DEFAULT 2,
                    activity_detection_enabled INTEGER NOT NULL DEFAULT 1,
                    no_person_seconds INTEGER NOT NULL,
                    offline_enabled INTEGER NOT NULL,
                    notification_enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO rules VALUES (
                    1, 17, 0.02, 19, 5, 0.24, 600, 1, 1, 1, 1,
                    0.55, 3, 5, 3, 1, 720, 1, 1, 'legacy-updated-at'
                );
                CREATE TABLE app_push_tokens (id INTEGER PRIMARY KEY);
                CREATE TABLE notification_deliveries (id INTEGER PRIMARY KEY, event_id INTEGER);
                """
            )

        storage = Storage(db_path)
        storage.init_schema()
        with storage.connect() as conn:
            tables = {
                str(row["name"])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            rule_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(rules)").fetchall()
            }

        if {"app_push_tokens", "notification_deliveries"} & tables:
            raise SystemExit("retired edge notification tables survived migration")
        if "notification_enabled" in rule_columns:
            raise SystemExit("retired edge notification rule survived migration")

        rules = storage.get_rules()
        if rules["capture_interval_seconds"] != 17 or rules["updated_at"] != "legacy-updated-at":
            raise SystemExit(f"notification migration changed retained rules: {rules}")
        updated = storage.update_rules({"capture_interval_seconds": 19, "notification_enabled": True})
        if updated["capture_interval_seconds"] != 19 or "notification_enabled" in updated:
            raise SystemExit(f"retired notification setting leaked through rule update: {updated}")


def main() -> None:
    retired_modules = {
        "apns_relay_service.py",
        "app_push_service.py",
        "edge_bootstrap_service.py",
        "notifier.py",
        "public_pilot_service.py",
    }
    existing_modules = sorted(name for name in retired_modules if (APP_DIR / name).exists())
    if existing_modules:
        raise SystemExit(f"retired edge runtime modules still exist: {existing_modules}")

    routes = decorated_routes(APP_DIR / "main.py")
    retired_routes = {
        "/api/v1/runtime/edge-service",
        "/api/v1/runtime/edge-service/install",
        "/api/v1/runtime/edge-service/reload",
        "/api/v1/runtime/edge-service/uninstall",
        "/api/v1/public-pilot/status",
        "/api/v1/notifications/deliveries",
        "/api/v1/notifications/test",
        "/api/v1/app/push-tokens",
        "/api/v1/app/push-tokens/{app_install_id}",
        "/api/v1/app/push-test",
        "/api/v1/runtime/app-push-relay",
        "/api/internal/app-push/relay",
        "/api/notify/test",
    }
    leaked_routes = sorted(retired_routes & routes)
    if leaked_routes:
        raise SystemExit(f"retired edge runtime routes remain: {leaked_routes}")

    main_tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
    mounted_paths = {
        str(node.args[0].value)
        for node in ast.walk(main_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mount"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    if "/ui" in mounted_paths:
        raise SystemExit("retired Web pilot remains mounted at /ui")

    forbidden_settings = {
        "frontend_dir",
        "edge_bootstrap_dir",
        "edge_bootstrap_logs_dir",
        "notify_channel",
        "generic_webhook_url",
        "feishu_webhook",
        "bark_url",
        "telegram_bot_token",
        "telegram_chat_id",
        "app_push_provider",
        "app_push_relay_url",
        "app_push_relay_secret",
        "apns_auth_key_path",
        "apns_key_id",
        "apns_team_id",
        "apns_topic",
    }
    leaked_settings = sorted(forbidden_settings & assigned_settings(APP_DIR / "settings.py"))
    if leaked_settings:
        raise SystemExit(f"retired edge settings remain: {leaked_settings}")

    env_source = (EDGE_ROOT / ".env.example").read_text(encoding="utf-8")
    forbidden_env_prefixes = ("GOHOME_NOTIFY_", "GOHOME_APNS_", "GOHOME_APP_PUSH_")
    leaked_env = sorted(
        line.split("=", 1)[0]
        for line in env_source.splitlines()
        if line.startswith(forbidden_env_prefixes)
    )
    if leaked_env:
        raise SystemExit(f"retired edge notification environment remains: {leaked_env}")

    event_tree = ast.parse((APP_DIR / "event_agent.py").read_text(encoding="utf-8"))
    event_attributes = {
        node.attr
        for node in ast.walk(event_tree)
        if isinstance(node, ast.Attribute)
    }
    if {"notifier", "send"} & event_attributes:
        raise SystemExit("edge event agent still owns direct notification delivery")

    deployment = (EDGE_ROOT / "scripts" / "install-systemd-service.sh").read_text(encoding="utf-8")
    required_systemd_contract = (
        "ExecStart=/bin/bash $RUN_SH",
        "Restart=always",
        "systemctl enable \"$SERVICE_NAME\"",
        "systemctl restart \"$SERVICE_NAME\"",
    )
    missing_systemd = [item for item in required_systemd_contract if item not in deployment]
    if missing_systemd:
        raise SystemExit(f"systemd production ownership contract is incomplete: {missing_systemd}")
    if "launchctl" in deployment or "LaunchAgent" in deployment:
        raise SystemExit("macOS LaunchAgent logic remains in production edge installer")

    cloud_server = CLOUD_SERVER.read_text(encoding="utf-8")
    cloud_provider = CLOUD_APNS_PROVIDER.read_text(encoding="utf-8")
    required_cloud_contract = (
        (cloud_server, 'require("./apns-provider")'),
        (cloud_server, 'pathname === "/api/v1/app/push-tokens"'),
        (cloud_server, "apnsProvider.send({"),
        (cloud_provider, "GOHOME_APNS_TEAM_ID"),
        (cloud_provider, "GOHOME_APNS_KEY_ID"),
        (cloud_provider, "GOHOME_APNS_TOPIC"),
    )
    missing_cloud = [needle for source, needle in required_cloud_contract if needle not in source]
    if missing_cloud:
        raise SystemExit(f"cloud APNs ownership contract is incomplete: {missing_cloud}")

    verify_legacy_database_migration()
    print(
        {
            "ok": True,
            "edge_notification_routes": 0,
            "edge_notification_modules": 0,
            "edge_web_pilot_mounts": 0,
            "edge_launchagent_owners": 0,
            "production_runtime_owner": "systemd",
            "notification_owner": "cloud",
            "legacy_schema_migrated": True,
        }
    )


if __name__ == "__main__":
    main()
