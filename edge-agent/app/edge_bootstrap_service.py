from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import json
import os
import plistlib
import shutil
import subprocess
import sys


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EdgeBootstrapService:
    def __init__(self, *, settings: Any) -> None:
        self.settings = settings

    @property
    def config_path(self) -> Path:
        return self.settings.edge_bootstrap_dir / "config.json"

    @property
    def bootstrap_script_path(self) -> Path:
        return self.settings.edge_bootstrap_dir / "bootstrap.py"

    @property
    def generated_plist_path(self) -> Path:
        return self.settings.edge_bootstrap_dir / f"{self.label}.plist"

    @property
    def stdout_log_path(self) -> Path:
        return self.settings.edge_bootstrap_logs_dir / "edge-bootstrap.log"

    @property
    def stderr_log_path(self) -> Path:
        return self.settings.edge_bootstrap_logs_dir / "edge-bootstrap.error.log"

    @property
    def label(self) -> str:
        return str(self.settings.edge_launch_agent_label or "com.gohome.edge-agent")

    @property
    def launch_agents_dir(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents"

    @property
    def installed_plist_path(self) -> Path:
        return self.launch_agents_dir / f"{self.label}.plist"

    def default_command(self) -> list[str]:
        return ["/bin/bash", str((self.settings.agent_root / "run.sh").resolve())]

    def default_env(self) -> Dict[str, str]:
        env: Dict[str, str] = {
            "GOHOME_AGENT_HOST": str(self.settings.host),
            "GOHOME_AGENT_PORT": str(self.settings.port),
            "GOHOME_AGENT_DATA_DIR": str(self.settings.data_dir),
            "GOHOME_AGENT_DB": str(self.settings.db_path),
            "GOHOME_DETECTOR_BACKEND": str(self.settings.detector_backend),
            "GOHOME_YOLO_MODEL": str(self.settings.yolo_model),
            "GOHOME_YOLO_CONFIDENCE": str(self.settings.yolo_confidence),
            "GOHOME_YOLO_IMGSZ": str(self.settings.yolo_imgsz),
            "GOHOME_NOTIFY_CHANNEL": str(self.settings.notify_channel),
        }
        optional_values = {
            "GOHOME_OBJECT_STORAGE_PROVIDER": str(self.settings.object_storage_provider),
            "GOHOME_OBJECT_STORAGE_BUCKET": str(self.settings.object_storage_bucket),
            "GOHOME_PUBLIC_BASE_URL": str(self.settings.public_base_url),
            "GOHOME_VIDEO_SERVICE_PUBLIC_BASE_URL": str(self.settings.video_service_public_base_url),
            "GOHOME_MEDIA_PUBLIC_BASE_URL": str(self.settings.media_public_base_url),
            "GOHOME_VIDEO_SERVICE_NODE_ID": str(self.settings.video_service_node_id),
            "GOHOME_VIDEO_SERVICE_REGION": str(self.settings.video_service_region),
            "GOHOME_VIDEO_SERVICE_ROLE": str(self.settings.video_service_role),
            "GOHOME_VIDEO_DISTRIBUTION_NAME": str(self.settings.video_distribution_name),
            "GOHOME_GENERIC_WEBHOOK_URL": str(self.settings.generic_webhook_url),
            "GOHOME_FEISHU_WEBHOOK": str(self.settings.feishu_webhook),
            "GOHOME_BARK_URL": str(self.settings.bark_url),
            "GOHOME_TELEGRAM_BOT_TOKEN": str(self.settings.telegram_bot_token),
            "GOHOME_TELEGRAM_CHAT_ID": str(self.settings.telegram_chat_id),
            "GOHOME_APP_PUSH_PROVIDER": str(self.settings.app_push_provider),
            "GOHOME_APP_PUSH_RELAY_URL": str(self.settings.app_push_relay_url),
            "GOHOME_APP_PUSH_RELAY_SECRET": str(self.settings.app_push_relay_secret),
            "GOHOME_APP_DEEP_LINK_SCHEME": str(self.settings.app_deep_link_scheme),
            "GOHOME_APNS_AUTH_KEY_PATH": str(self.settings.apns_auth_key_path),
            "GOHOME_APNS_KEY_ID": str(self.settings.apns_key_id),
            "GOHOME_APNS_TEAM_ID": str(self.settings.apns_team_id),
            "GOHOME_APNS_TOPIC": str(self.settings.apns_topic),
            "GOHOME_APNS_DEFAULT_ENVIRONMENT": str(self.settings.apns_default_environment),
            "GOHOME_APNS_REQUEST_TIMEOUT_SECONDS": str(self.settings.apns_request_timeout_seconds),
        }
        for key, value in optional_values.items():
            clean = str(value or "").strip()
            if clean:
                env[key] = clean
        return env

    def default_config(self) -> Dict[str, Any]:
        target = str((self.settings.agent_root / "run.sh").resolve())
        return {
            "label": self.label,
            "target_path": target,
            "command": self.default_command(),
            "cwd": str(self.settings.agent_root.resolve()),
            "env": self.default_env(),
            "bootstrap_script_path": str(self.bootstrap_script_path),
            "generated_plist_path": str(self.generated_plist_path),
            "stdout_log_path": str(self.stdout_log_path),
            "stderr_log_path": str(self.stderr_log_path),
            "updated_at": now_iso(),
        }

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self.default_config()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        merged = {**self.default_config(), **data}
        merged["command"] = [str(item) for item in merged.get("command") or self.default_command()]
        merged["env"] = {str(key): str(value) for key, value in dict(merged.get("env") or {}).items()}
        return merged

    def write_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        merged = {**self.load_config(), **(payload or {}), "updated_at": now_iso()}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def write_bootstrap_script(self) -> Path:
        self.bootstrap_script_path.parent.mkdir(parents=True, exist_ok=True)
        script = f"""#!/usr/bin/env python3
from pathlib import Path
import json
import os
import sys

CONFIG_PATH = Path({self.config_path.as_posix()!r})

def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = os.environ.copy()
    env.update({{str(key): str(value) for key, value in dict(config.get("env") or {{}}).items()}})
    cwd = str(config.get("cwd") or Path.cwd())
    command = [str(item) for item in (config.get("command") or [])]
    if not command:
        raise SystemExit("bootstrap command is empty")
    os.chdir(cwd)
    os.execvpe(command[0], command, env)

if __name__ == "__main__":
    main()
"""
        self.bootstrap_script_path.write_text(script, encoding="utf-8")
        self.bootstrap_script_path.chmod(0o755)
        return self.bootstrap_script_path

    def write_generated_plist(self, config: Dict[str, Any]) -> Path:
        self.generated_plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_payload = {
            "Label": self.label,
            "ProgramArguments": [sys.executable, str(self.bootstrap_script_path)],
            "RunAtLoad": True,
            "KeepAlive": True,
            "WorkingDirectory": str(config.get("cwd") or self.settings.agent_root),
            "StandardOutPath": str(self.stdout_log_path),
            "StandardErrorPath": str(self.stderr_log_path),
            "EnvironmentVariables": {
                "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
                "PYTHONUNBUFFERED": "1",
            },
        }
        with self.generated_plist_path.open("wb") as handle:
            plistlib.dump(plist_payload, handle, sort_keys=True)
        return self.generated_plist_path

    def ensure_bootstrap_assets(self) -> Dict[str, Any]:
        config = self.write_config()
        self.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_bootstrap_script()
        self.write_generated_plist(config)
        return config

    def launchctl_domain_target(self) -> str:
        return f"gui/{os.getuid()}/{self.label}"

    def run_launchctl(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        if sys.platform != "darwin":
            raise RuntimeError("launchd orchestration is only supported on macOS")
        result = subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or f"launchctl {' '.join(args)} failed").strip()
            raise RuntimeError(detail)
        return result

    def status(self) -> Dict[str, Any]:
        config = self.ensure_bootstrap_assets()
        installed = self.installed_plist_path.exists()
        print_result = None
        loaded = False
        if installed:
            print_result = self.run_launchctl("print", self.launchctl_domain_target())
            loaded = print_result.returncode == 0
        return {
            "label": self.label,
            "platform": sys.platform,
            "target_path": str(config.get("target_path") or ""),
            "command": list(config.get("command") or []),
            "cwd": str(config.get("cwd") or ""),
            "env": dict(config.get("env") or {}),
            "env_files": list(getattr(self.settings, "env_files", []) or []),
            "config_path": str(self.config_path),
            "bootstrap_script_path": str(self.bootstrap_script_path),
            "generated_plist_path": str(self.generated_plist_path),
            "installed_plist_path": str(self.installed_plist_path),
            "stdout_log_path": str(self.stdout_log_path),
            "stderr_log_path": str(self.stderr_log_path),
            "installed": installed,
            "loaded": loaded,
            "launchctl_status_code": None if print_result is None else int(print_result.returncode),
            "launchctl_excerpt": ""
            if print_result is None
            else str((print_result.stdout or print_result.stderr or "").strip()[:500]),
        }

    def install(self) -> Dict[str, Any]:
        self.ensure_bootstrap_assets()
        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.generated_plist_path, self.installed_plist_path)
        self.run_launchctl("bootout", self.launchctl_domain_target())
        self.run_launchctl("bootstrap", f"gui/{os.getuid()}", str(self.installed_plist_path), check=True)
        self.run_launchctl("kickstart", "-k", self.launchctl_domain_target(), check=True)
        return {
            **self.status(),
            "action": "install",
            "installed_at": now_iso(),
        }

    def reload(self) -> Dict[str, Any]:
        if not self.installed_plist_path.exists():
            raise RuntimeError("LaunchAgent is not installed")
        self.ensure_bootstrap_assets()
        shutil.copy2(self.generated_plist_path, self.installed_plist_path)
        self.run_launchctl("bootout", self.launchctl_domain_target())
        self.run_launchctl("bootstrap", f"gui/{os.getuid()}", str(self.installed_plist_path), check=True)
        self.run_launchctl("kickstart", "-k", self.launchctl_domain_target(), check=True)
        return {
            **self.status(),
            "action": "reload",
            "reloaded_at": now_iso(),
        }

    def uninstall(self) -> Dict[str, Any]:
        installed_before = self.installed_plist_path.exists()
        self.run_launchctl("bootout", self.launchctl_domain_target())
        if self.installed_plist_path.exists():
            self.installed_plist_path.unlink()
        return {
            **self.status(),
            "action": "uninstall",
            "installed_before": installed_before,
            "uninstalled_at": now_iso(),
        }
