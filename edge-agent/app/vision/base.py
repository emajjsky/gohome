from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass
class AlgorithmResult:
    algorithm_id: str
    label: str
    status: str
    score: float | None = None
    level: str = "info"
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload["score"] is not None:
            payload["score"] = round(float(payload["score"]), 4)
        return payload


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
