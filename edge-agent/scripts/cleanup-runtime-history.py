from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import settings
from app.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely prune routine edge runtime history.")
    parser.add_argument("--retention-hours", type=int, default=settings.history_retention_hours)
    parser.add_argument("--upload-retention-days", type=int, default=settings.completed_upload_retention_days)
    parser.add_argument("--batch-size", type=int, default=settings.history_cleanup_batch_size)
    parser.add_argument("--until-complete", action="store_true")
    args = parser.parse_args()

    storage = Storage(settings.db_path)
    total: dict[str, int] = {}
    deleted_files = 0
    passes = 0
    while True:
        result = storage.prune_runtime_history(
            snapshot_dir=settings.snapshot_dir,
            retention_hours=args.retention_hours,
            completed_upload_retention_days=args.upload_retention_days,
            batch_size=args.batch_size,
        )
        passes += 1
        for table, count in result["deleted"].items():
            total[table] = total.get(table, 0) + int(count)
        deleted_files += int(result["deleted_snapshot_files"])
        if not args.until_complete or not result["has_more"]:
            break

    print(json.dumps({
        "ok": True,
        "passes": passes,
        "deleted": total,
        "deleted_snapshot_files": deleted_files,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
