from __future__ import annotations

from typing import Any, Callable


DEFAULT_SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)

# OpenCV uses BGR. This is the single normal skeleton style for every edge-composed view.
SKELETON_LINE_BGR = (219, 209, 33)
SKELETON_JOINT_BGR = (255, 255, 255)
SKELETON_OUTLINE_BGR = (8, 8, 8)
SKELETON_LINE_WIDTH = 3
SKELETON_OUTLINE_WIDTH = 6
SKELETON_JOINT_RADIUS = 3
SKELETON_JOINT_OUTLINE_RADIUS = 5
SKELETON_BOX_BGR = SKELETON_LINE_BGR
SKELETON_BOX_WIDTH = 2


def visible_pose_points(pose: dict[str, Any], *, minimum_confidence: float = 0.22) -> dict[str, dict[str, Any]]:
    return {
        str(point.get("name")): point
        for point in (pose.get("keypoints") or [])
        if isinstance(point, dict)
        and point.get("name")
        and point.get("visible")
        and float(point.get("confidence") or 0.0) >= minimum_confidence
    }


def draw_skeleton_pose(
    cv2: Any,
    canvas: Any,
    pose: dict[str, Any],
    edges: Any,
    point_resolver: Callable[[dict[str, Any]], tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    points = visible_pose_points(pose)
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) < 2:
            continue
        start = points.get(str(edge[0]))
        end = points.get(str(edge[1]))
        if start is None or end is None:
            continue
        p1 = point_resolver(start)
        p2 = point_resolver(end)
        cv2.line(canvas, p1, p2, SKELETON_OUTLINE_BGR, SKELETON_OUTLINE_WIDTH, cv2.LINE_AA)
        cv2.line(canvas, p1, p2, SKELETON_LINE_BGR, SKELETON_LINE_WIDTH, cv2.LINE_AA)
    for point in points.values():
        center = point_resolver(point)
        cv2.circle(canvas, center, SKELETON_JOINT_OUTLINE_RADIUS, SKELETON_OUTLINE_BGR, -1, cv2.LINE_AA)
        cv2.circle(canvas, center, SKELETON_JOINT_RADIUS, SKELETON_JOINT_BGR, -1, cv2.LINE_AA)
    return points
