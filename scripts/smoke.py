"""Smoke test against the real Sonarr/Radarr/Prowlarr using `.env`.

Calls every **read-only** tool (it refuses to call anything that is not
annotated readOnlyHint=True) and prints a one-line summary per tool.

    python scripts/smoke.py                 # run all read-only tools
    python scripts/smoke.py --verbose       # also print each JSON result
    python scripts/smoke.py --capture       # also save raw API responses,
                                            # anonymized, to scripts/captures/

Captured files are git-ignored. Review them before copying anything into
tests/fixtures/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import Client  # noqa: E402

from arr_doctor.clients.base import ArrClient, ArrError  # noqa: E402
from arr_doctor.config import Settings  # noqa: E402
from arr_doctor.server import _configure_logging, build_server  # noqa: E402
from arr_doctor.tools.common import Services  # noqa: E402

CAPTURE_DIR = Path(__file__).resolve().parent / "captures"

# Default arguments for tools that need them; filled in at runtime from the library.
DEFAULT_ARGS: dict[str, dict[str, Any]] = {
    "get_logs": {"limit": 5},
    "get_history": {"limit": 10},
    "get_calendar": {"days_ahead": 7, "days_back": 3},
    "find_suspicious_releases": {"days": 30},
}
SKIP = {
    "get_command_status",  # needs a command id from a write tool
    "explain_search",  # queries every indexer live; try it by hand from the MCP client
    "test_download_clients",  # connects to the download clients; try it by hand
}


async def run_tools(settings: Settings, verbose: bool) -> int:
    server = build_server(settings)
    failures = 0
    async with Client(server) as client:
        tools = await client.list_tools()
        read_only = [t for t in tools if t.annotations and t.annotations.readOnlyHint is True]
        skipped_write = sorted(t.name for t in tools if t not in read_only)

        # Pick a real series / movie to exercise the per-item tools.
        lib = await client.call_tool("search_library", {"limit": 500}, raise_on_error=False)
        items = (lib.structured_content or {}).get("items", []) if not lib.is_error else []
        series = next((i for i in items if i["type"] == "series"), None)
        movie = next((i for i in items if i["type"] == "movie"), None)
        first_service = "sonarr" if settings.sonarr else "radarr"
        DEFAULT_ARGS["diagnose_import"] = {"service": first_service}
        if series:
            DEFAULT_ARGS["parse_release"] = {
                "title": f"{series['title'].replace(' ', '.')}.S01E01.1080p.WEB.H264-SMOKE", "service": "sonarr"
            }
            DEFAULT_ARGS["get_series"] = {"series": series["id"]}
            DEFAULT_ARGS["preview_rename"] = {"series": series["id"], "limit": 5}
            DEFAULT_ARGS["get_episodes"] = {"series": series["id"], "limit": 5}
        if movie:
            DEFAULT_ARGS["get_movie"] = {"movie": movie["id"]}
            DEFAULT_ARGS.setdefault("preview_rename", {"movie": movie["id"], "limit": 5})
            DEFAULT_ARGS.setdefault(
                "parse_release",
                {"title": f"{movie['title'].replace(' ', '.')}.{movie.get('year', 2020)}.1080p.BluRay.x264-SMOKE",
                 "service": "radarr"},
            )

        for tool in sorted(read_only, key=lambda t: t.name):
            if tool.name in SKIP or (tool.name in {"get_series", "get_episodes"} and not series) or (
                tool.name in {"parse_release", "preview_rename"} and tool.name not in DEFAULT_ARGS
            ) or (
                tool.name == "get_movie" and not movie
            ):
                print(f"  SKIP  {tool.name}")
                continue
            args = DEFAULT_ARGS.get(tool.name, {})
            start = time.monotonic()
            res = await client.call_tool(tool.name, args, raise_on_error=False)
            elapsed = time.monotonic() - start
            text = res.content[0].text if res.content else ""
            if res.is_error:
                failures += 1
                print(f"  FAIL  {tool.name:<26} {elapsed:5.1f}s  {text}")
            else:
                print(f"  ok    {tool.name:<26} {elapsed:5.1f}s  {len(text):>7} chars")
                if verbose:
                    print(json.dumps(res.structured_content, indent=2, ensure_ascii=False)[:4000])
        print(f"\nWrite tools NOT called: {', '.join(skipped_write) or '-'}")
    return failures


# ------------------------------------------------------------------ capture

_SECRET_KEYS = re.compile(r"(api_?key|password|passkey|cookie|token|secret|username|rsskey)", re.I)


def anonymize(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SECRET_KEYS.search(k):
                out[k] = "<redacted>"
            elif k == "fields" and isinstance(v, list):  # Prowlarr / provider settings
                out[k] = [{**f, "value": "<redacted>"} if "value" in f else f for f in v if isinstance(f, dict)]
            elif k in {"remoteUrl", "remotePoster", "guid", "torrentInfoHash", "downloadUrl"}:
                out[k] = "<redacted>"
            elif k in {"images", "overview"}:
                out[k] = [] if k == "images" else "Overview removed."
            else:
                out[k] = anonymize(v)
        return out
    if isinstance(obj, list):
        return [anonymize(v) for v in obj]
    return obj


async def capture(svc: Services) -> None:
    CAPTURE_DIR.mkdir(exist_ok=True)
    plan: list[tuple[ArrClient | None, str, str, dict[str, Any]]] = [
        (svc.sonarr, "sonarr_system_status", "/system/status", {}),
        (svc.sonarr, "sonarr_queue", "/queue", {"includeSeries": True, "includeEpisode": True, "pageSize": 50}),
        (svc.sonarr, "sonarr_history", "/history", {"pageSize": 20, "includeSeries": True, "includeEpisode": True}),
        (svc.sonarr, "sonarr_blocklist", "/blocklist", {"pageSize": 20}),
        (svc.sonarr, "sonarr_health", "/health", {}),
        (svc.sonarr, "sonarr_wanted_missing", "/wanted/missing", {"pageSize": 10, "includeSeries": True}),
        (svc.sonarr, "sonarr_qualityprofile", "/qualityprofile", {}),
        (svc.sonarr, "sonarr_rootfolder", "/rootfolder", {}),
        (svc.sonarr, "sonarr_diskspace", "/diskspace", {}),
        (svc.radarr, "radarr_system_status", "/system/status", {}),
        (svc.radarr, "radarr_queue", "/queue", {"includeMovie": True, "pageSize": 50}),
        (svc.radarr, "radarr_history", "/history", {"pageSize": 20, "includeMovie": True}),
        (svc.radarr, "radarr_blocklist", "/blocklist", {"pageSize": 20}),
        (svc.radarr, "radarr_wanted_missing", "/wanted/missing", {"pageSize": 10}),
        (svc.prowlarr, "prowlarr_indexers", "/indexer", {}),
        (svc.prowlarr, "prowlarr_indexerstatus", "/indexerstatus", {}),
    ]
    if svc.sonarr:
        plan.append(
            (svc.sonarr, "sonarr_manualimport_downloads", "/manualimport",
             {"folder": svc.settings.arr_downloads_path, "filterExistingFiles": True})
        )
    for client, name, path, params in plan:
        if client is None:
            continue
        try:
            data = await client.request("GET", path, params=params, timeout=180)
        except ArrError as exc:
            print(f"  FAIL  capture {name}: {exc}")
            continue
        (CAPTURE_DIR / f"{name}.json").write_text(
            json.dumps(anonymize(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  saved {name}.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()

    _configure_logging()
    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    settings = Settings()
    if not (settings.sonarr or settings.radarr):
        sys.exit("No hay servicios configurados: rellena .env (ver .env.example).")
    print("Servicios:", ", ".join(n for n in ("sonarr", "radarr", "prowlarr") if getattr(settings, n)))
    failures = asyncio.run(run_tools(settings, args.verbose))
    if args.capture:
        asyncio.run(capture(Services.from_settings(settings)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
