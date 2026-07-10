from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "eval"
API_URL = "https://commons.wikimedia.org/w/api.php"
TITLES = [
    "File:Calhoun living room.jpg",
    "File:Empty apartment living room.jpg",
    "File:HK Shatin 大圍 溱岸8號 Riverpark empty showflat living room Dec-2012.JPG",
    "File:Living room (4102748829).jpg",
    "File:Mostly Empty Living Room (30977076047).jpg",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download curated CC/public-domain empty-room negatives.")
    parser.add_argument("--samples-dir", type=Path, default=DATA_ROOT / "samples" / "person" / "wikimedia_indoor_negative")
    parser.add_argument("--thumb-width", type=int, default=1280)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    return parser.parse_args()


def safe_name(title: str, index: int) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64]
    return f"{index:02d}-{stem or 'indoor-negative'}.jpg"


def fetch_metadata(thumb_width: int) -> list[dict]:
    params = {
        "action": "query",
        "titles": "|".join(TITLES),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": str(thumb_width),
        "format": "json",
        "formatversion": "2",
    }
    request = Request(f"{API_URL}?{urlencode(params)}", headers={"User-Agent": "GoHomeVisionEval/1.0"})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    return list(payload.get("query", {}).get("pages", []))


def download_image(url: str, target: Path, retries: int) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    curl = shutil.which("curl")
    if curl:
        completed = subprocess.run(
            [
                curl,
                "-fL",
                "--retry",
                str(max(1, retries)),
                "--retry-all-errors",
                "--connect-timeout",
                "20",
                "--max-time",
                "180",
                "-A",
                "GoHomeVisionEval/1.0",
                "-o",
                str(temporary),
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0 and temporary.exists() and temporary.stat().st_size > 0:
            temporary.replace(target)
            return
        temporary.unlink(missing_ok=True)

    last_error: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            request = Request(url, headers={"User-Agent": "GoHomeVisionEval/1.0"})
            with urlopen(request, timeout=30) as response, temporary.open("wb") as handle:
                while chunk := response.read(1024 * 256):
                    handle.write(chunk)
            temporary.replace(target)
            return
        except (OSError, URLError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {last_error}") from last_error


def main() -> None:
    args = parse_args()
    samples_dir = args.samples_dir.resolve()
    samples_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = samples_dir / "metadata.json"
    if args.no_download:
        pages = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        pages = fetch_metadata(args.thumb_width)
        metadata_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")

    by_title = {str(page.get("title")): page for page in pages}
    entries = []
    for index, title in enumerate(TITLES, start=1):
        page = by_title.get(title)
        if not page or not page.get("imageinfo"):
            raise RuntimeError(f"missing Wikimedia metadata: {title}")
        info = page["imageinfo"][0]
        metadata = info.get("extmetadata") or {}
        url = info.get("thumburl") or info.get("url")
        target = samples_dir / safe_name(title, index)
        if not args.no_download and (args.force or not target.exists()):
            download_image(url, target, args.retries)
        if not target.exists():
            raise FileNotFoundError(target)
        entries.append({
            "file": target.name,
            "person": False,
            "source_dataset": "Wikimedia Commons curated indoor negatives",
            "source_title": title,
            "source_url": info.get("descriptionurl"),
            "license": (metadata.get("LicenseShortName") or {}).get("value", ""),
            "artist": (metadata.get("Artist") or {}).get("value", ""),
            "label_note": "manually curated empty room / furniture negative",
            "config": {"pose_detection_enabled": True},
        })

    manifest = samples_dir / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")
    print(json.dumps({"ok": True, "dataset": "Wikimedia Commons indoor negatives", "count": len(entries), "manifest": str(manifest)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
