from __future__ import annotations


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

