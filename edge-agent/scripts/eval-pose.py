from __future__ import annotations

from eval_vision_common import parse_common_args, run_eval


def main() -> None:
    parser = parse_common_args("Evaluate pose/keypoint samples.", "pose")
    parser.set_defaults(pose_enabled=True)
    args = parser.parse_args()
    run_eval(
        task="pose",
        args=args,
        label_keys=["pose", "pose_present", "has_pose", "keypoints", "label", "expected"],
        predict=lambda analysis: int(analysis.get("pose_count") or 0) > 0,
        detail=lambda analysis: {
            "pose_count": analysis.get("pose_count"),
            "pose_model_status": analysis.get("pose_model_status"),
            "pose_model_name": analysis.get("pose_model_name"),
            "pose_action_hints": analysis.get("pose_action_hints"),
            "pose_fall_score": analysis.get("pose_fall_score"),
        },
    )


if __name__ == "__main__":
    main()
