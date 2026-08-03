from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
ADMIN = ROOT / "edge-agent" / "admin"
EXPECTED_HTML = {
    "algorithms.html",
    "cameras.html",
    "events.html",
    "index.html",
    "login.html",
}
EXPECTED_JS = {"console.js", "login.js"}
EXPECTED_ASSETS: set[str] = set()
EXPECTED_PAGE_SCRIPTS = {
    "algorithms.html": ["console.js"],
    "cameras.html": ["console.js"],
    "events.html": ["console.js"],
    "index.html": ["console.js"],
    "login.html": ["login.js"],
}


class ScriptSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        source = dict(attrs).get("src")
        if source:
            self.sources.append(source)


def local_admin_script(source: str) -> str | None:
    path = urlsplit(source).path
    prefix = "/admin/"
    if not path.startswith(prefix):
        return None
    return path.removeprefix(prefix)


def main() -> None:
    actual_html = {path.name for path in ADMIN.glob("*.html")}
    actual_js = {path.name for path in ADMIN.glob("*.js")}
    actual_assets = {
        path.relative_to(ADMIN).as_posix()
        for path in (ADMIN / "assets").glob("**/*")
        if path.is_file()
    }
    if actual_html != EXPECTED_HTML:
        raise SystemExit({"unexpected_html": sorted(actual_html - EXPECTED_HTML), "missing_html": sorted(EXPECTED_HTML - actual_html)})
    if actual_js != EXPECTED_JS:
        raise SystemExit({"unexpected_js": sorted(actual_js - EXPECTED_JS), "missing_js": sorted(EXPECTED_JS - actual_js)})
    if actual_assets != EXPECTED_ASSETS:
        raise SystemExit({
            "unexpected_assets": sorted(actual_assets - EXPECTED_ASSETS),
            "missing_assets": sorted(EXPECTED_ASSETS - actual_assets),
        })

    dependencies: dict[str, list[str]] = {}
    for page_name in sorted(EXPECTED_HTML):
        parser = ScriptSourceParser()
        parser.feed((ADMIN / page_name).read_text(encoding="utf-8"))
        scripts = [name for source in parser.sources if (name := local_admin_script(source))]
        dependencies[page_name] = scripts
        if scripts != EXPECTED_PAGE_SCRIPTS[page_name]:
            raise SystemExit({"page": page_name, "expected_scripts": EXPECTED_PAGE_SCRIPTS[page_name], "actual_scripts": scripts})
        missing = [name for name in scripts if not (ADMIN / name).is_file()]
        if missing:
            raise SystemExit({"page": page_name, "missing_dependencies": missing})

    console_source = (ADMIN / "console.js").read_text(encoding="utf-8")
    required_stream_contracts = {
        "stream generation": "streamGeneration: 0",
        "fresh image element": "function replaceLiveStreamElement()",
        "old load handler removal": "current.onload = null",
        "old error handler removal": "current.onerror = null",
        "old request cancellation": 'current.removeAttribute("src")',
        "old image removal": "current.replaceWith(stream)",
        "hidden before first frame": 'stream.style.visibility = "hidden"',
        "visible after first frame": 'stream.style.visibility = "visible"',
        "stale session rejection": "generation !== state.streamGeneration",
        "calibration request ownership": "privacyCalibrationPendingCameraIds: new Set()",
    }
    missing_contracts = [
        label for label, source in required_stream_contracts.items()
        if source not in console_source
    ]
    if missing_contracts:
        raise SystemExit({"missing_admin_runtime_contracts": missing_contracts})
    if "streamMaskTimer" in console_source:
        raise SystemExit({"forbidden_admin_runtime_contract": "timer-based stream reveal"})
    generation_index = console_source.index("const generation = ++state.streamGeneration")
    replacement_index = console_source.index("const stream = replaceLiveStreamElement()", generation_index)
    if generation_index >= replacement_index:
        raise SystemExit({"forbidden_admin_runtime_contract": "old stream retired before generation advance"})

    print({
        "ok": True,
        "pages": sorted(EXPECTED_HTML),
        "scripts": sorted(EXPECTED_JS),
        "assets": sorted(EXPECTED_ASSETS),
        "dependencies": dependencies,
        "runtime_contracts": sorted(required_stream_contracts),
    })


if __name__ == "__main__":
    main()
