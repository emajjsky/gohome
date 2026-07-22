from __future__ import annotations

from typing import Any, Dict, Optional


class EventAgent:
    def __init__(self, storage: Any, notifier: Any, throttle_seconds: int) -> None:
        self.storage = storage
        self.notifier = notifier
        self.throttle_seconds = throttle_seconds

    def emit(
        self,
        event_type: str,
        summary: str,
        level: str = "warning",
        camera: Optional[Dict[str, Any]] = None,
        snapshot_id: Optional[int] = None,
        detection_result_id: Optional[int] = None,
        rule_evaluation_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        camera_id = camera["id"] if camera else None
        throttle_seconds = self._throttle_seconds(event_type)
        if not force:
            if candidate_id is not None:
                aggregated = self.storage.aggregate_event_candidate_into_recent_event(
                    candidate_id=int(candidate_id),
                    camera_id=camera_id,
                    event_type=event_type,
                    seconds=throttle_seconds,
                )
                if aggregated is not None:
                    return None
            elif self.storage.event_exists_recent(camera_id, event_type, throttle_seconds):
                return None

        event = self.storage.create_event(
            event_type=event_type,
            summary=summary,
            level=level,
            camera_id=camera_id,
            room=(camera or {}).get("room", ""),
            snapshot_id=snapshot_id,
            detection_result_id=detection_result_id,
            rule_evaluation_id=rule_evaluation_id,
            candidate_id=candidate_id,
            payload=payload or {},
        )
        if candidate_id is not None:
            self.storage.update_event_candidate_status(candidate_id, "promoted", promoted_event_id=event["id"])

        self.storage.enqueue_event_upload_jobs(event)

        rules = self.storage.get_rules()
        if rules.get("notification_enabled") and self._should_notify(event_type, level):
            self.notifier.send(
                title="回家告警",
                body=summary,
                extra={
                    "event_id": event["id"],
                    "event_type": event_type,
                    "camera_id": camera_id,
                    "room": (camera or {}).get("room", ""),
                },
            )

        return event

    def _throttle_seconds(self, event_type: str) -> int:
        if event_type == "fall_candidate":
            return max(3, min(self.throttle_seconds, 8))
        if event_type == "prolonged_floor_lying":
            return max(30, min(self.throttle_seconds, 60))
        if event_type in {"no_motion", "no_person"}:
            return max(self.throttle_seconds, 3600)
        if event_type == "fire_candidate":
            return max(self.throttle_seconds, 1800)
        if event_type in {"black_screen", "camera_offline"}:
            return max(self.throttle_seconds, 900)
        return self.throttle_seconds

    def _should_notify(self, event_type: str, level: str) -> bool:
        if level != "critical":
            return False
        return event_type in {"fall_candidate", "prolonged_floor_lying", "fire_candidate", "camera_offline"}
