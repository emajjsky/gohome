from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult, clamp


class FallAnalyzer:
    def analyze(self, people: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        weak_candidates = [person for person in people if person.get("fall_candidate") and not self._is_strong_box_candidate(person, config)]
        candidates = [person for person in people if self._is_strong_box_candidate(person, config)]
        single_low_body = self._single_low_body_candidate(people, config)
        cluster = self._floor_cluster_candidate(people, config)
        score = 0.0
        for person in people:
            if person in weak_candidates:
                continue
            aspect_ratio = float(person.get("aspect_ratio") or 0.0)
            center_y_ratio = float(person.get("center_y_ratio") or 0.0)
            area_ratio = float(person.get("area_ratio") or 0.0)
            score = max(score, clamp((aspect_ratio - 1.15) / 1.1) * 0.55 + clamp(center_y_ratio - 0.38) * 0.25 + clamp(area_ratio / 0.16) * 0.2)
        if cluster:
            score = max(score, float(cluster.get("score") or 0.0))
        if single_low_body:
            score = max(score, float(single_low_body.get("score") or 0.0))
        fall_candidate = bool(candidates) or bool(single_low_body) or bool(cluster)
        candidate_payload = [*candidates]
        if single_low_body:
            candidate_payload.append(single_low_body)
        if cluster:
            candidate_payload.append(cluster)
        result = AlgorithmResult(
            algorithm_id="fall",
            label="跌倒候选",
            status="candidate" if fall_candidate else "clear",
            score=score if people else None,
            level="critical" if fall_candidate else "info",
            summary="检测到疑似倒地姿态。" if fall_candidate else "未命中跌倒候选。",
            tags=["fall_candidate"] if fall_candidate else [],
            data={
                "fall_candidate": fall_candidate,
                "candidate_count": len(candidate_payload),
                "people": candidate_payload,
                "weak_people": weak_candidates,
                "method": "person_box_and_floor_cluster",
                "single_low_body": single_low_body,
                "floor_cluster": cluster,
            },
        )
        return {
            "fall_candidate": fall_candidate,
            "fall_score": score if people else None,
            "tags": ["fall_candidate"] if fall_candidate else [],
            "result": result,
        }

    def _is_strong_box_candidate(self, person: Dict[str, Any], config: Dict[str, Any]) -> bool:
        if not person.get("fall_candidate") or person.get("presence_candidate"):
            return False
        confidence = person.get("confidence")
        min_confidence = float(config.get("fall_box_min_confidence", 0.30))
        if confidence is None:
            return False
        return float(confidence) >= min_confidence

    def _single_low_body_candidate(self, people: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any] | None:
        if not config.get("fall_single_low_body_enabled", True):
            return None

        candidates: list[Dict[str, Any]] = []
        for person in people:
            if person.get("presence_candidate"):
                continue
            bbox = person.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            confidence = person.get("confidence")
            min_confidence = float(config.get("fall_box_min_confidence", 0.30))
            if confidence is None or float(confidence) < min_confidence:
                continue
            frame_height = int(person.get("frame_height") or 0)
            if frame_height <= 0:
                continue
            area_ratio = float(person.get("area_ratio") or 0.0)
            height_ratio = float(person.get("height_ratio") or 0.0)
            aspect_ratio = float(person.get("aspect_ratio") or 0.0)
            center_y_ratio = float(person.get("center_y_ratio") or 0.0)
            floor_contact = float(bbox[3]) / max(1, frame_height)

            min_aspect = float(config.get("fall_single_low_body_min_aspect", 0.85))
            min_area = float(config.get("fall_single_low_body_min_area", 0.055))
            max_area = float(config.get("fall_single_low_body_max_area", 0.24))
            min_center_y = float(config.get("fall_single_low_body_min_center_y", 0.78))
            max_height = float(config.get("fall_single_low_body_max_height", 0.46))
            min_floor_contact = float(config.get("fall_single_low_body_min_floor_contact", 0.88))

            if not (
                aspect_ratio >= min_aspect
                and min_area <= area_ratio <= max_area
                and center_y_ratio >= min_center_y
                and height_ratio <= max_height
                and floor_contact >= min_floor_contact
            ):
                continue

            score = (
                clamp((aspect_ratio - min_aspect) / 0.8) * 0.26
                + clamp((center_y_ratio - min_center_y) / 0.16) * 0.32
                + clamp((floor_contact - min_floor_contact) / 0.12) * 0.26
                + clamp((area_ratio - min_area) / 0.14) * 0.16
            )
            candidates.append(
                {
                    **person,
                    "source": "fall_single_low_body",
                    "label": "低位倒地人体",
                    "method": "low_body_floor_contact",
                    "floor_contact": round(floor_contact, 3),
                    "score": round(score, 4),
                    "fall_candidate": True,
                }
            )
        if not candidates:
            return None
        return max(candidates, key=lambda item: float(item.get("score") or 0.0))

    def _floor_cluster_candidate(self, people: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any] | None:
        if not config.get("fall_floor_cluster_enabled", True):
            return None

        low_people = []
        for person in people:
            bbox = person.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            area_ratio = float(person.get("area_ratio") or 0.0)
            height_ratio = float(person.get("height_ratio") or 0.0)
            center_y_ratio = float(person.get("center_y_ratio") or 0.0)
            if area_ratio >= 0.025 and height_ratio >= 0.16 and center_y_ratio >= 0.58:
                low_people.append(person)

        min_fragments = int(config.get("fall_floor_cluster_min_fragments", 3))
        if len(low_people) < max(2, min_fragments):
            return None

        frame_width = int(low_people[0].get("frame_width") or 0)
        frame_height = int(low_people[0].get("frame_height") or 0)
        if frame_width <= 0 or frame_height <= 0:
            return None

        xs1 = [float(person["bbox"][0]) for person in low_people]
        ys1 = [float(person["bbox"][1]) for person in low_people]
        xs2 = [float(person["bbox"][2]) for person in low_people]
        ys2 = [float(person["bbox"][3]) for person in low_people]
        x1, y1, x2, y2 = min(xs1), min(ys1), max(xs2), max(ys2)
        box_width = max(1.0, x2 - x1)
        box_height = max(1.0, y2 - y1)
        aspect_ratio = box_width / box_height
        area_ratio = (box_width * box_height) / max(1, frame_width * frame_height)
        height_ratio = box_height / max(1, frame_height)
        center_y_ratio = ((y1 + y2) / 2.0) / max(1, frame_height)
        floor_contact = y2 / max(1, frame_height)

        min_aspect = float(config.get("fall_floor_cluster_min_aspect", 1.05))
        min_area = float(config.get("fall_floor_cluster_min_area", 0.06))
        max_area = float(config.get("fall_floor_cluster_max_area", 0.38))
        min_center_y = float(config.get("fall_floor_cluster_min_center_y", 0.62))
        max_height = float(config.get("fall_floor_cluster_max_height", 0.66))
        min_floor_contact = float(config.get("fall_floor_cluster_min_floor_contact", 0.80))

        if not (
            aspect_ratio >= min_aspect
            and min_area <= area_ratio <= max_area
            and center_y_ratio >= min_center_y
            and height_ratio <= max_height
            and floor_contact >= min_floor_contact
        ):
            return None

        score = (
            clamp((aspect_ratio - min_aspect) / 0.7) * 0.34
            + clamp((center_y_ratio - min_center_y) / 0.2) * 0.28
            + clamp((floor_contact - min_floor_contact) / 0.18) * 0.22
            + clamp((area_ratio - min_area) / 0.18) * 0.16
        )
        return {
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "confidence": round(max(0.56, min(0.88, 0.52 + score * 0.34)), 4),
            "source": "fall_floor_cluster",
            "label": "贴地人体簇",
            "presence_candidate": False,
            "method": "merged_low_body_fragments",
            "aspect_ratio": round(aspect_ratio, 3),
            "area_ratio": round(area_ratio, 4),
            "height_ratio": round(height_ratio, 3),
            "center_y_ratio": round(center_y_ratio, 3),
            "floor_contact": round(floor_contact, 3),
            "fragment_count": len(low_people),
            "score": round(score, 4),
            "fall_candidate": True,
        }
