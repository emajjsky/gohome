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
        if not force and self.storage.event_exists_recent(camera_id, event_type, self.throttle_seconds):
            if candidate_id is not None:
                self.storage.update_event_candidate_status(candidate_id, "suppressed")
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

        rules = self.storage.get_rules()
        if rules.get("notification_enabled"):
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
