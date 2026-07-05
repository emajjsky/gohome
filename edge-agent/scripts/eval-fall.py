from __future__ import annotations

from eval_vision_common import parse_common_args, run_eval


def main() -> None:
    parser = parse_common_args("Evaluate fall detection samples.", "fall")
    parser.add_argument("--use-pose", action="store_true", help="Enable RTMPose while evaluating fall samples.")
    args = parser.parse_args()
    if args.use_pose:
        args.pose_enabled = True
    run_eval(
        task="fall",
        args=args,
        label_keys=["fall", "fallen", "fall_candidate", "label", "expected"],
        predict=lambda analysis: bool(analysis.get("fall_candidate") or analysis.get("pose_fall_candidate")),
        detail=lambda analysis: {
            "fall_candidate": analysis.get("fall_candidate"),
            "fall_score": analysis.get("fall_score"),
            "pose_fall_candidate": analysis.get("pose_fall_candidate"),
            "pose_fall_score": analysis.get("pose_fall_score"),
            "person_count": analysis.get("person_count"),
            "pose_count": analysis.get("pose_count"),
        },
    )


if __name__ == "__main__":
    main()
