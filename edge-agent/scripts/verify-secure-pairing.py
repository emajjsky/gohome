from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config_sync_agent import ConfigSyncAgent
from app.device_binding_state import DeviceBindingState
from app.pairing_window import PairingWindow


def main() -> None:
    monotonic_now = [100.0]
    wall_now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    window = PairingWindow(
        900,
        monotonic_clock=lambda: monotonic_now[0],
        wall_clock=lambda: wall_now,
    )
    assert window.status()["remaining_seconds"] == 900
    monotonic_now[0] += 901
    assert not window.is_open()
    reopened = window.open(600)
    assert reopened["open"] and reopened["remaining_seconds"] == 600
    assert not window.close()["open"]

    with tempfile.TemporaryDirectory() as tmpdir:
        state = DeviceBindingState(Path(tmpdir) / "binding.json")
        stored = state.write({
            "status": "bound",
            "family_name": "测试家庭",
            "owner_account": "138****2550",
            "owner_display_name": "家庭创建者",
            "bound_at": "2026-07-25T12:00:00Z",
            "raw_phone": "13818462550",
            "device_token": "must-not-persist",
        })
        assert stored["owner_account"] == "138****2550"
        persisted = (Path(tmpdir) / "binding.json").read_text(encoding="utf-8")
        assert "13818462550" not in persisted and "must-not-persist" not in persisted

        callbacks: list[dict | None] = []
        agent = ConfigSyncAgent(
            storage=SimpleNamespace(),
            settings=SimpleNamespace(
                app_server_base_url="https://cloud.example",
                config_sync_enabled=True,
                config_sync_request_timeout_seconds=2,
                require_issued_device_token=True,
                device_api_token="",
                runtime_dir=Path(tmpdir) / "runtime",
            ),
            camera_agent=SimpleNamespace(),
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "revoked-token",
            presence_status_resolver=lambda *_args, **_kwargs: {},
            binding_summary_writer=callbacks.append,
        )
        error = HTTPError(
            "https://cloud.example/api/v1/device/config",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"error":"invalid device token"}'),
        )
        with patch("app.config_sync_agent.urlopen", side_effect=error):
            try:
                agent._request_json("GET", "/api/v1/device/config")
            except RuntimeError:
                pass
            else:
                raise AssertionError("revoked device token must fail config sync")
        assert callbacks == [None]

    print("secure pairing verification passed")


if __name__ == "__main__":
    main()
