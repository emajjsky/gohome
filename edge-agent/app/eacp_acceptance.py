from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable, Dict
from uuid import uuid4


SAFETY_EVENT_TYPES = {"fall_candidate", "prolonged_floor_lying", "fire_candidate"}
NEGATIVE_SCENARIOS = {"walking", "fast_sit", "squat", "sofa_lying"}
SUPPORTED_SCENARIOS = {*NEGATIVE_SCENARIOS, "simulated_fall", "custom"}


class EacpAcceptanceService:
    """Build a bounded acceptance timeline without changing inference or alert policy."""

    schema_version = "eacp-acceptance-v1"

    def __init__(
        self,
        *,
        state_path: Path,
        runtime_resolver: Callable[[], Dict[str, Any]],
        events_resolver: Callable[[], list[Dict[str, Any]]],
        candidates_resolver: Callable[[], list[Dict[str, Any]]],
        uploads_resolver: Callable[[], list[Dict[str, Any]]],
        cloud_verification_resolver: Callable[[], Dict[str, Any]],
        utcnow: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.runtime_resolver = runtime_resolver
        self.events_resolver = events_resolver
        self.candidates_resolver = candidates_resolver
        self.uploads_resolver = uploads_resolver
        self.cloud_verification_resolver = cloud_verification_resolver
        self.utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._session = self._load()

    def start(self, *, scenario: str, camera_id: int, label: str = "") -> Dict[str, Any]:
        scenario = str(scenario or "").strip().lower()
        if scenario not in SUPPORTED_SCENARIOS:
            raise ValueError(f"unsupported acceptance scenario: {scenario}")
        camera_id = int(camera_id)
        if camera_id <= 0:
            raise ValueError("camera_id must be positive")
        runtime = self.runtime_resolver() or {}
        events = self.events_resolver() or []
        candidates = self.candidates_resolver() or []
        started_at = self._utc_iso(self.utcnow())
        started_monotonic = float(self.monotonic_clock())
        self._session = {
            "schema_version": self.schema_version,
            "session_id": uuid4().hex,
            "status": "active",
            "scenario": scenario,
            "label": str(label or "").strip(),
            "camera_id": camera_id,
            "started_at": started_at,
            "started_at_monotonic": started_monotonic,
            "finished_at": None,
            "baseline": {
                "runtime": self._camera_runtime(runtime, camera_id),
                "max_event_id": max((int(item.get("id") or 0) for item in events), default=0),
                "max_candidate_id": max((int(item.get("id") or 0) for item in candidates), default=0),
            },
        }
        self._save(self._session)
        return self.status()

    def status(self) -> Dict[str, Any]:
        if not self._session:
            return {"schema_version": self.schema_version, "status": "idle"}
        if self._session.get("status") == "finished" and isinstance(self._session.get("report"), dict):
            return deepcopy(self._session["report"])
        return self._build_report(self._session, finalizing=False)

    def finish(self) -> Dict[str, Any]:
        if not self._session or self._session.get("status") != "active":
            raise ValueError("no active acceptance session")
        report = self._build_report(self._session, finalizing=True)
        report["status"] = "finished"
        report["finished_at"] = self._utc_iso(self.utcnow())
        self._session = {**self._session, "status": "finished", "finished_at": report["finished_at"], "report": report}
        self._save(self._session)
        return deepcopy(report)

    def clear(self) -> Dict[str, Any]:
        self._session = {}
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {"schema_version": self.schema_version, "status": "idle"}

    def _build_report(self, session: Dict[str, Any], *, finalizing: bool) -> Dict[str, Any]:
        now = self.utcnow()
        now_mono = float(self.monotonic_clock())
        camera_id = int(session["camera_id"])
        runtime = self.runtime_resolver() or {}
        current = self._camera_runtime(runtime, camera_id)
        baseline = (session.get("baseline") or {}).get("runtime") or {}
        elapsed = max(0.001, now_mono - float(session.get("started_at_monotonic") or now_mono))
        events = self._new_camera_rows(
            self.events_resolver() or [],
            camera_id=camera_id,
            minimum_id=int((session.get("baseline") or {}).get("max_event_id") or 0),
        )
        candidates = self._new_camera_rows(
            self.candidates_resolver() or [],
            camera_id=camera_id,
            minimum_id=int((session.get("baseline") or {}).get("max_candidate_id") or 0),
        )
        uploads = self.uploads_resolver() or []
        safety_events = [
            event for event in sorted(events, key=lambda item: int(item.get("id") or 0))
            if self._event_type(event) in SAFETY_EVENT_TYPES
        ]
        cloud_payload: Dict[str, Any] = {
            "ok": False,
            "reason": "no_safety_event",
            "records": [],
        }
        if safety_events:
            try:
                cloud_payload = self.cloud_verification_resolver() or {}
            except Exception as exc:
                cloud_payload = {"ok": False, "reason": str(exc), "records": []}
        cloud_records = cloud_payload.get("records") if isinstance(cloud_payload.get("records"), list) else []

        event_reports = [
            self._event_report(event, uploads=uploads, cloud_records=cloud_records, started_at=session["started_at"])
            for event in safety_events
        ]
        metrics = self._metrics(
            baseline=baseline,
            current=current,
            elapsed=elapsed,
            started_monotonic=float(session.get("started_at_monotonic") or now_mono),
        )
        checks = self._checks(
            scenario=str(session.get("scenario") or "custom"),
            events=event_reports,
            finalizing=finalizing,
        )
        result = self._result(checks, finalizing=finalizing)
        return {
            "schema_version": self.schema_version,
            "session_id": session["session_id"],
            "status": str(session.get("status") or "active"),
            "result": result,
            "scenario": session["scenario"],
            "label": session.get("label") or "",
            "camera_id": camera_id,
            "started_at": session["started_at"],
            "finished_at": session.get("finished_at"),
            "elapsed_seconds": round(elapsed, 3),
            "metrics": metrics,
            "checks": checks,
            "events": event_reports,
            "candidate_count": len(candidates),
            "cloud": {
                "ok": bool(cloud_payload.get("ok")),
                "reason": str(cloud_payload.get("reason") or ""),
            },
            "runtime_health": {
                "worker_error": str(runtime.get("last_error") or ""),
                "continual_pose_error": str(runtime.get("continual_pose_error") or ""),
                "managed_stream_count": int((runtime.get("camera_streams") or {}).get("managed_stream_count") or 0),
                "temperature_c": (runtime.get("inference_scheduler") or {}).get("resource", {}).get("temperature_c"),
                "thermal_state": str((runtime.get("inference_scheduler") or {}).get("resource", {}).get("thermal_state") or "unknown"),
            },
            "observed_at": self._utc_iso(now),
        }

    def _camera_runtime(self, runtime: Dict[str, Any], camera_id: int) -> Dict[str, Any]:
        scheduler = self._camera_item((runtime.get("inference_scheduler") or {}).get("cameras"), camera_id)
        continual = self._camera_item((runtime.get("continual_pose") or {}).get("cameras"), camera_id)
        return {"scheduler": scheduler, "continual": continual}

    def _metrics(
        self,
        *,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        elapsed: float,
        started_monotonic: float,
    ) -> Dict[str, Any]:
        before_schedule = baseline.get("scheduler") or {}
        schedule = current.get("scheduler") or {}
        before_continual = baseline.get("continual") or {}
        continual = current.get("continual") or {}
        anchor_count = max(0, int(schedule.get("observed_count") or 0) - int(before_schedule.get("observed_count") or 0))
        risk_count = max(0, int(schedule.get("risk_signal_count") or 0) - int(before_schedule.get("risk_signal_count") or 0))
        hint_count = max(0, int(continual.get("risk_hint_count") or 0) - int(before_continual.get("risk_hint_count") or 0))
        risk_times = [
            float(item.get("at_monotonic"))
            for item in schedule.get("risk_signals") or []
            if isinstance(item, dict) and item.get("at_monotonic") is not None
            and float(item["at_monotonic"]) >= started_monotonic
        ]
        if not risk_times and risk_count:
            last_risk = schedule.get("last_risk_signal_at_monotonic")
            if last_risk is not None and float(last_risk) >= started_monotonic:
                risk_times.append(float(last_risk))
        first_risk_latency = min(risk_times) - started_monotonic if risk_times else None
        return {
            "mode": str(schedule.get("mode") or "unknown"),
            "model_anchor_count": anchor_count,
            "model_anchor_fps": round(anchor_count / elapsed, 3),
            "reported_effective_fps": schedule.get("effective_fps"),
            "deadline_miss_count": max(
                0,
                int(schedule.get("deadline_miss_count") or 0) - int(before_schedule.get("deadline_miss_count") or 0),
            ),
            "risk_signal_count": risk_count,
            "risk_hint_count": hint_count,
            "first_risk_latency_seconds": None if first_risk_latency is None else round(max(0.0, first_risk_latency), 3),
            "tracked_frame_count": max(
                0,
                int(continual.get("tracked_count") or 0) - int(before_continual.get("tracked_count") or 0),
            ),
        }

    def _event_report(
        self,
        event: Dict[str, Any],
        *,
        uploads: list[Dict[str, Any]],
        cloud_records: list[Dict[str, Any]],
        started_at: str,
    ) -> Dict[str, Any]:
        event_id = int(event.get("id") or 0)
        event_uploads = [item for item in uploads if int(item.get("event_id") or 0) == event_id]
        media = [item for item in event_uploads if item.get("job_type") == "media_upload"]
        event_job = next((item for item in event_uploads if item.get("job_type") == "event_upload"), None)
        cloud_record = next(
            (
                item for item in cloud_records
                if str(item.get("edge_event_id") or item.get("event_id") or "") == str(event_id)
            ),
            None,
        )
        verification = (cloud_record or {}).get("verification")
        if not isinstance(verification, dict):
            verification = (cloud_record or {}).get("incident") if isinstance((cloud_record or {}).get("incident"), dict) else {}
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        bundle = evidence.get("temporal_evidence_bundle") if isinstance(evidence.get("temporal_evidence_bundle"), dict) else {}
        if not bundle and isinstance(payload.get("temporal_evidence_bundle"), dict):
            bundle = payload["temporal_evidence_bundle"]
        snapshots = bundle.get("snapshots") if isinstance(bundle.get("snapshots"), list) else []
        assets = payload.get("evidence_media_assets") if isinstance(payload.get("evidence_media_assets"), list) else []
        evidence_frame_count = max(len(snapshots), len(assets), len(media))
        occurred_at = str(event.get("occurred_at") or event.get("created_at") or "")
        return {
            "event_id": event_id,
            "event_type": self._event_type(event),
            "level": str(event.get("level") or ""),
            "occurred_at": occurred_at,
            "event_latency_seconds": self._seconds_between(started_at, occurred_at),
            "evidence_frame_count": evidence_frame_count,
            "media_upload_completed": sum(1 for item in media if item.get("status") == "completed"),
            "event_upload_status": str((event_job or {}).get("status") or "missing"),
            "cloud_verification": {
                "status": str(verification.get("status") or "pending"),
                "confidence": verification.get("confidence"),
            },
        }

    def _checks(self, *, scenario: str, events: list[Dict[str, Any]], finalizing: bool) -> Dict[str, str]:
        safety_event = bool(events)
        if scenario in NEGATIVE_SCENARIOS:
            return {
                "unexpected_safety_event": "failed" if safety_event else "passed" if finalizing else "observing",
            }
        if scenario == "simulated_fall":
            fall = next((item for item in events if item.get("event_type") == "fall_candidate"), None)
            return {
                "simulated_fall_event": "passed" if fall else "failed" if finalizing else "pending",
                "three_frame_evidence": (
                    "passed" if fall and int(fall.get("evidence_frame_count") or 0) >= 3
                    else "failed" if finalizing else "pending"
                ),
                "event_uploaded": (
                    "passed" if fall and fall.get("event_upload_status") == "completed"
                    else "failed" if finalizing else "pending"
                ),
                "cloud_verified": (
                    "passed" if fall and fall.get("cloud_verification", {}).get("status") in {"confirmed", "rejected", "uncertain"}
                    else "failed" if finalizing else "pending"
                ),
            }
        return {"manual_review": "pending" if not finalizing else "incomplete"}

    def _result(self, checks: Dict[str, str], *, finalizing: bool) -> str:
        if any(value == "failed" for value in checks.values()):
            return "failed"
        if not finalizing:
            return "observing"
        return "passed" if checks and all(value == "passed" for value in checks.values()) else "incomplete"

    def _new_camera_rows(self, rows: list[Dict[str, Any]], *, camera_id: int, minimum_id: int) -> list[Dict[str, Any]]:
        return [
            item for item in rows
            if int(item.get("id") or 0) > minimum_id and int(item.get("camera_id") or 0) == camera_id
        ]

    def _event_type(self, event: Dict[str, Any]) -> str:
        return str(event.get("event_type") or event.get("type") or "")

    def _camera_item(self, rows: Any, camera_id: int) -> Dict[str, Any]:
        if not isinstance(rows, list):
            return {}
        return deepcopy(next((item for item in rows if int(item.get("camera_id") or 0) == camera_id), {}))

    def _seconds_between(self, first: str, second: str) -> float | None:
        try:
            start = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(second).replace("Z", "+00:00"))
            return round(max(0.0, (end - start).total_seconds()), 3)
        except (TypeError, ValueError):
            return None

    def _utc_iso(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def _load(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, value: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)
