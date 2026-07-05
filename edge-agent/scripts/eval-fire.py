from __future__ import annotations

from eval_vision_common import parse_common_args, run_eval


def main() -> None:
    parser = parse_common_args("Evaluate fire/smoke samples.", "fire")
    parser.add_argument(
        "--target",
        choices=["visual", "event"],
        default="event",
        help="visual checks single-frame fire visual clues; event checks formal temporal event candidate.",
    )
    args = parser.parse_args()
    if args.target == "visual":
        label_keys = ["fire", "smoke", "fire_visual", "fire_candidate", "label", "expected"]
        predict = lambda analysis: bool(analysis.get("fire_candidate"))
    else:
        label_keys = ["fire_event", "fire", "smoke", "label", "expected"]
        predict = lambda analysis: bool(analysis.get("fire_event_candidate"))
    run_eval(
        task=f"fire_{args.target}",
        args=args,
        label_keys=label_keys,
        predict=predict,
        detail=lambda analysis: {
            "fire_candidate": analysis.get("fire_candidate"),
            "fire_event_candidate": analysis.get("fire_event_candidate"),
            "fire_score": analysis.get("fire_score"),
            "fire_temporal_score": analysis.get("fire_temporal_score"),
            "motion_score": analysis.get("motion_score"),
            "fire_features": analysis.get("fire_features"),
        },
    )


if __name__ == "__main__":
    main()
