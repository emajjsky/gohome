from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable, Dict
import json
import os
import signal
import subprocess
import sys
import time


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppRuntimeGuardService:
    def __init__(
        self,
        *,
        settings: Any,
        current_manifest_loader: Callable[[], Dict[str, Any]],
    ) -> None:
        self.settings = settings
        self.current_manifest_loader = current_manifest_loader
        self._state_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def state_path(self) -> Path:
        return self.settings.app_runtime_dir / "state.json"

    @property
    def stdout_log_path(self) -> Path:
        return self.settings.runtime_logs_dir / "app-runtime.log"

    def load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = {**self.load_state(), **payload, "updated_at": now_iso()}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def is_running_pid(self, pid: int | None) -> bool:
        if not pid:
            return False
        try:
            finished_pid, _status = os.waitpid(int(pid), os.WNOHANG)
            if finished_pid == int(pid):
                return False
        except ChildProcessError:
            pass
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    def runnable_entry(self, manifest: Dict[str, Any]) -> Path:
        installed_path = str(manifest.get("installed_path") or "").strip()
        if not installed_path:
            raise RuntimeError("App manifest missing installed_path")
        entry = Path(installed_path)
        if not entry.exists():
            raise RuntimeError(f"App entry does not exist: {entry}")
        if entry.is_dir():
            raise RuntimeError("App installed_path must resolve to a concrete entry file")
        return entry.resolve()

    def is_runnable_manifest(self, manifest: Dict[str, Any]) -> bool:
        try:
            self.build_command(manifest)
            return True
        except Exception:
            return False

    def build_command(self, manifest: Dict[str, Any]) -> list[str]:
        entry = self.runnable_entry(manifest)
        suffix = entry.suffix.lower()
        if suffix == ".py":
            return [sys.executable, str(entry)]
        if suffix == ".sh":
            return ["/bin/bash", str(entry)]
        if os.access(entry, os.X_OK):
            return [str(entry)]
        raise RuntimeError(f"Unsupported app entrypoint: {entry.name}")

    def stop_runtime(self, *, clear_should_run: bool) -> Dict[str, Any]:
        with self._state_lock:
            state = self.load_state()
            pid = int(state.get("pid") or 0) if state.get("pid") else 0
            if pid and self.is_running_pid(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                deadline = time.time() + 3
                while time.time() < deadline and self.is_running_pid(pid):
                    time.sleep(0.1)
                if self.is_running_pid(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
            return self.write_state(
                {
                    "pid": None,
                    "running": False,
                    "should_run": False if clear_should_run else bool(state.get("should_run")),
                    "stopped_at": now_iso(),
                }
            )

    def _spawn_manifest(self, manifest: Dict[str, Any], *, restart_count: int) -> Dict[str, Any]:
        command = self.build_command(manifest)
        entry = self.runnable_entry(manifest)
        self.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = self.stdout_log_path.open("ab")
        env = os.environ.copy()
        env["GOHOME_RUNTIME_VERSION"] = str(manifest.get("version") or "")
        process = subprocess.Popen(
            command,
            cwd=str(entry.parent),
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        state = self.write_state(
            {
                "pid": int(process.pid),
                "running": True,
                "should_run": True,
                "version": str(manifest.get("version") or ""),
                "installed_path": str(manifest.get("installed_path") or ""),
                "started_at": now_iso(),
                "restart_count": int(restart_count),
                "last_error": "",
                "last_exit_code": None,
                "command": command,
                "log_path": str(self.stdout_log_path),
            }
        )
        time.sleep(max(0.2, float(self.settings.app_runtime_startup_grace_seconds)))
        exit_code = process.poll()
        if exit_code is not None:
            failed = self.write_state(
                {
                    "pid": None,
                    "running": False,
                    "should_run": False,
                    "last_error": f"process exited during startup with code {exit_code}",
                    "last_exit_code": int(exit_code),
                    "failed_at": now_iso(),
                }
            )
            return {"ok": False, "state": failed, "error": failed["last_error"]}
        return {"ok": True, "state": state}

    def apply_release(self, manifest: Dict[str, Any], *, previous_manifest: Dict[str, Any] | None = None) -> Dict[str, Any]:
        previous = dict(previous_manifest or {})
        previous_state = self.load_state()
        previous_should_run = bool(previous_state.get("should_run"))
        self.stop_runtime(clear_should_run=False)
        result = self._spawn_manifest(manifest, restart_count=0)
        if result["ok"]:
            return {
                "ok": True,
                "rolled_back": False,
                "version": str(manifest.get("version") or ""),
                "state": result["state"],
            }
        rollback_ok = False
        rollback_error = ""
        if previous and self.is_runnable_manifest(previous):
            rollback = self._spawn_manifest(previous, restart_count=int(previous_state.get("restart_count") or 0))
            rollback_ok = bool(rollback["ok"])
            rollback_error = "" if rollback_ok else str(rollback.get("error") or "")
            if not previous_should_run:
                self.stop_runtime(clear_should_run=True)
        else:
            self.stop_runtime(clear_should_run=True)
        return {
            "ok": False,
            "rolled_back": rollback_ok,
            "error": result.get("error") or "apply release failed",
            "rollback_error": rollback_error,
            "active_version": str(previous.get("version") or ""),
        }

    def restart_current(self) -> Dict[str, Any]:
        manifest = dict(self.current_manifest_loader() or {})
        if not manifest:
            raise RuntimeError("Current app manifest is empty")
        self.stop_runtime(clear_should_run=False)
        return self._spawn_manifest(manifest, restart_count=0)

    def status(self) -> Dict[str, Any]:
        state = self.load_state()
        pid = int(state.get("pid") or 0) if state.get("pid") else 0
        running = self.is_running_pid(pid)
        if state.get("running") != running:
            state = self.write_state({"running": running, "pid": pid if running else None})
        return {
            "running": running,
            "pid": pid if running else None,
            "should_run": bool(state.get("should_run")),
            "version": str(state.get("version") or ""),
            "restart_count": int(state.get("restart_count") or 0),
            "last_error": str(state.get("last_error") or ""),
            "last_exit_code": state.get("last_exit_code"),
            "installed_path": str(state.get("installed_path") or ""),
            "log_path": str(state.get("log_path") or self.stdout_log_path),
            "current_manifest": dict(self.current_manifest_loader() or {}),
        }

    def _watch_loop(self) -> None:
        interval = max(0.5, float(self.settings.app_runtime_watchdog_interval_seconds))
        while not self._stop_event.wait(interval):
            state = self.load_state()
            if not bool(state.get("should_run")):
                continue
            if self.is_running_pid(int(state.get("pid") or 0)):
                continue
            manifest = dict(self.current_manifest_loader() or {})
            if not manifest or not self.is_runnable_manifest(manifest):
                self.write_state({"running": False, "pid": None, "last_error": "Current manifest is not runnable"})
                continue
            restart_count = int(state.get("restart_count") or 0) + 1
            self._spawn_manifest(manifest, restart_count=restart_count)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._watch_loop, name="gohome-app-runtime-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
