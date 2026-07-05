from __future__ import annotations

from eval_vision_common import parse_common_args, run_eval


def main() -> None:
    parser = parse_common_args("Evaluate person detection samples.", "person")
    args = parser.parse_args()
    run_eval(
        task="person",
        args=args,
        label_keys=["person", "person_present", "has_person", "label", "expected"],
        predict=lambda analysis: int(analysis.get("person_count") or 0) > 0,
        detail=lambda analysis: {
            "person_count": analysis.get("person_count"),
            "presence_enhanced": analysis.get("presence_enhanced"),
            "model_status": analysis.get("model_status"),
            "model_name": analysis.get("model_name"),
        },
    )


if __name__ == "__main__":
    main()
