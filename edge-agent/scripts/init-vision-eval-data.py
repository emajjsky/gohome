from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "eval" / "vision_dataset_catalog.json"
DATA_ROOT = ROOT / "data" / "eval"

RAW_DATASETS = [
    "coco",
    "open_images",
    "dfire",
    "ur_fall",
    "fire_smoke_video",
    "ntu_rgbd",
    "eatsense",
    "kinetics",
    "ucf101",
    "virat",
]

SAMPLE_TASKS = [
    "person",
    "pose",
    "fall",
    "fire",
    "activity",
    "quality",
    "negative",
]


def load_catalog() -> dict:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_readme(path: Path, title: str, body: str) -> None:
    readme = path / "README.md"
    if readme.exists():
        return
    readme.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")


def main() -> None:
    catalog = load_catalog()
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for group in ["raw", "samples", "reports", "manifests"]:
        (DATA_ROOT / group).mkdir(parents=True, exist_ok=True)

    dataset_by_folder = {dataset["id"].replace("-", "_"): dataset for dataset in catalog.get("datasets", [])}
    for folder in RAW_DATASETS:
        path = DATA_ROOT / "raw" / folder
        path.mkdir(parents=True, exist_ok=True)
        dataset = dataset_by_folder.get(folder)
        if dataset is None:
            dataset = next((item for item in catalog.get("datasets", []) if folder in item["id"].replace("-", "_")), None)
        if dataset:
            write_readme(
                path,
                dataset["name"],
                "\n".join(
                    [
                        f"- URL: {dataset['url']}",
                        f"- Tasks: {', '.join(dataset.get('tasks', []))}",
                        f"- Priority: {dataset.get('priority', '')}",
                        f"- Access: {dataset.get('access', '')}",
                        f"- Local importer: {dataset.get('local_importer', 'not implemented')}",
                        f"- Note: {dataset.get('fit_for_gohome', '')}",
                        f"- Caveats: {'; '.join(dataset.get('caveats', []))}",
                    ]
                ),
            )

    for task in SAMPLE_TASKS:
        path = DATA_ROOT / "samples" / task
        path.mkdir(parents=True, exist_ok=True)
        write_readme(
            path,
            f"{task} samples",
            "Put curated, small evaluation samples here. Do not commit raw datasets to Git.",
        )

    write_readme(
        DATA_ROOT,
        "GoHome vision evaluation data",
        "This directory is local-only. Keep raw datasets, curated samples, manifests, and evaluation reports here.",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "data_root": str(DATA_ROOT),
                "raw_dataset_dirs": len(RAW_DATASETS),
                "sample_task_dirs": len(SAMPLE_TASKS),
                "catalog": str(CATALOG_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required file: {exc}") from exc
