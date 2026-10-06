"""Diagnostic tools: queue, history, blocklist, health, logs, disk, orphans, suspicious releases."""

from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from arr_doctor import formatting as fmt
from arr_doctor import paths
from arr_doctor.clients import radarr as radarr_api
from arr_doctor.clients import sonarr as sonarr_api
from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t, t_opt
from arr_doctor.tools.common import (
    READ_ONLY,
    ServiceOpt,
    ServiceReq,
    Services,
    per_service,
    resolve_movie,
    resolve_series,
    returns_candidates,
)
from arr_doctor.tools.importcheck import import_targets, verify_import
from arr_doctor.tools.troubleshoot import STALL_HOURS, parse_date, stall_reason

Limit = Annotated[int, Field(ge=1, le=500, description="Max items to return")]

HistoryEvent = Literal["grabbed", "imported", "failed", "deleted", "renamed", "ignored"]

_EVENT_MAP: dict[str, dict[str, int]] = {
    "sonarr": {
        "grabbed": sonarr_api.HISTORY_EVENT_TYPES["grabbed"],
        "imported": sonarr_api.HISTORY_EVENT_TYPES["downloadFolderImported"],
        "failed": sonarr_api.HISTORY_EVENT_TYPES["downloadFailed"],
        "deleted": sonarr_api.HISTORY_EVENT_TYPES["episodeFileDeleted"],
        "renamed": sonarr_api.HISTORY_EVENT_TYPES["episodeFileRenamed"],
        "ignored": sonarr_api.HISTORY_EVENT_TYPES["downloadIgnored"],
    },
    "radarr": {
        "grabbed": radarr_api.HISTORY_EVENT_TYPES["grabbed"],
        "imported": radarr_api.HISTORY_EVENT_TYPES["downloadFolderImported"],
        "failed": radarr_api.HISTORY_EVENT_TYPES["downloadFailed"],
        "deleted": radarr_api.HISTORY_EVENT_TYPES["movieFileDeleted"],
        "renamed": radarr_api.HISTORY_EVENT_TYPES["movieFileRenamed"],
        "ignored": radarr_api.HISTORY_EVENT_TYPES["downloadIgnored"],
    },
}

SUSPICIOUS_EXTENSIONS = ("exe", "scr", "lnk", "bat", "cmd", "msi", "zipx")
_EXT = "|".join(SUSPICIOUS_EXTENSIONS)
SUSPICIOUS_RE = re.compile(r"\.(" + _EXT + r")(?![a-z0-9])", re.IGNORECASE)
# Sonarr/Radarr store release titles normalized: "...H264-VICE.exe" becomes
# "...H264 VICE exe". At the very end of a title, a space/_/- also counts.
SUSPICIOUS_TITLE_END_RE = re.compile(r"[\s_\-](" + _EXT + r")\s*$", re.IGNORECASE)

# Scanning the whole downloads folder can be slow on a NAS.
_SCAN_TIMEOUT = 180.0

_PROBLEM_STATES = {"importBlocked", "importPending", "failedPending", "failed"}


def find_suspicious_extensions(*texts: str | None, titles: tuple[str | None, ...] = ()) -> list[str]:
    """Suspicious extensions in free text (".exe") and at the end of release titles
    (also "VICE exe", as Sonarr/Radarr store them)."""
    found: set[str] = set()
    for text in (*texts, *titles):
        if text:
            found.update(m.lower() for m in SUSPICIOUS_RE.findall(text))
    for title in titles:
        if title:
            found.update(m.lower() for m in SUSPICIOUS_TITLE_END_RE.findall(title))
    return sorted(found)


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_queue(
        service: ServiceOpt = None,
        only_problems: Annotated[
            bool, Field(description="Only items with warnings/errors or blocked imports")
        ] = False,
        include_unknown: Annotated[
            bool, Field(description="Also list downloads in the client that Sonarr/Radarr did not grab")
        ] = False,
        limit: Limit = fmt.DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Download queue with tracked state (downloading, importBlocked, importPending, failed…),
        status messages explaining why an import is stuck, indexer and download client.
        Downloads that Sonarr/Radarr did not grab themselves are hidden (as in the web UI) and
        only counted, unless include_unknown=true. Stalled downloads (no activity, no metadata,
        no progress for 6 h) are marked with stall_reason and count as problems, even when
        Sonarr/Radarr report them as healthy.

        Examples: "What's stuck in the queue and why?", "Is S03E04 of The Capture still downloading?"
        """
        async def one(name: str, client: Any) -> Any:
            page, everything = await asyncio.gather(
                client.queue(include_unknown=include_unknown), client.queue(page_size=1, include_unknown=True)
            )
            hidden = 0 if include_unknown else max(0, (everything.get("totalRecords") or 0) - (page.get("totalRecords") or 0))
            now = datetime.now(UTC)
            items = []
            for group in fmt.group_queue(page.get("records") or []):
                item = fmt.queue_items(group, name)[0]
                first = group[0]
                stall = stall_reason(first, now, STALL_HOURS, parse_date(first.get("added")))
                if stall:
                    item["stall_reason"] = stall
                items.append(item)
            if only_problems:
                items = [
                    i
                    for i in items
                    if i.get("health") in ("warning", "error")
                    or i.get("state") in _PROBLEM_STATES
                    or i.get("error")
                    or i.get("stall_reason")
                ]
            states = Counter(i.get("state", "unknown") for i in items)
            extra: dict[str, Any] = {"by_state": dict(states)}
            stalled = sum(1 for i in items if i.get("stall_reason"))
            if stalled:
                extra["stalled"] = stalled
            if hidden:
                extra["unknown_items_hidden"] = hidden
            return fmt.limited(items, limit, **extra)

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    @returns_candidates
    async def get_history(
        service: ServiceOpt = None,
        series: Annotated[str | int | None, Field(description="Sonarr series ID or title")] = None,
        movie: Annotated[str | int | None, Field(description="Radarr movie ID or title")] = None,
        event_type: HistoryEvent | None = None,
        days: Annotated[int | None, Field(ge=1, le=365, description="Only the last N days")] = None,
        limit: Limit = fmt.DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Activity history: grabs (with indexer), imports, failed downloads, deletions.

        Examples: "Which indexer did S03E04 of The Capture come from?",
        "What failed to download in the last 7 days?"
        """
        if series is not None:
            service = "sonarr"
        elif movie is not None:
            service = "radarr"
        async def one(name: str, client: Any) -> Any:
            item_id: int | None = None
            if name == "sonarr" and series is not None:
                item_id = (await resolve_series(svc.require_sonarr(), series))["id"]
            if name == "radarr" and movie is not None:
                item_id = (await resolve_movie(svc.require_radarr(), movie))["id"]
            ev = _EVENT_MAP[name][event_type] if event_type else None
            id_key = "seriesId" if name == "sonarr" else "movieId"

            if days:
                since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
                records = await client.history_since(since, ev)
                if item_id is not None:
                    records = [r for r in records if r.get(id_key) == item_id]
                records.sort(key=lambda r: r.get("date") or "", reverse=True)
                total = len(records)
            else:
                if name == "sonarr":
                    page = await svc.require_sonarr().history(limit, series_id=item_id, event_type=ev)
                else:
                    page = await svc.require_radarr().history(limit, movie_id=item_id, event_type=ev)
                records = page.get("records") or []
                total = page.get("totalRecords", len(records))
            return fmt.limited([fmt.history_item(r, name) for r in records], limit, total=total)

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_blocklist(service: ServiceOpt = None, limit: Limit = fmt.DEFAULT_LIMIT) -> dict[str, Any]:
        """Blocklisted releases with the indexer they came from and the reason.

        Examples: "What's in the blocklist?", "Which indexer has the most blocklisted releases?"
        """
        async def one(name: str, client: Any) -> Any:
            page = await client.blocklist(limit)
            items = [fmt.blocklist_item(b, name) for b in page.get("records") or []]
            by_indexer = Counter(i.get("indexer", "unknown") for i in items)
            return fmt.limited(
                items, limit, total=page.get("totalRecords"), by_indexer_in_page=dict(by_indexer)
            )

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_health(service: ServiceOpt = None) -> dict[str, Any]:
        """Health warnings and errors reported by Sonarr/Radarr (and Prowlarr if configured):
        unreachable download client, missing root folder, indexers failing… each with the
        usual fix when it is a known check.

        Examples: "Any health warnings?", "Is something wrong with Radarr?"
        """
        targets: list[tuple[str, Any]] = list(svc.arrs(service))
        if service is None and svc.prowlarr:
            targets.append(("prowlarr", svc.prowlarr))

        async def one(client: Any) -> list[dict[str, Any]] | dict[str, str]:
            try:
                checks = await client.health()
            except ArrError as exc:
                return {"error": str(exc)}
            return [
                fmt.drop_none(
                    {
                        "type": c.get("type"),
                        "source": c.get("source"),
                        "message": c.get("message"),
                        "fix": t_opt(f"health_{c.get('source')}"),
                        "wiki": c.get("wikiUrl"),
                    }
                )
                for c in checks
            ]

        results = await asyncio.gather(*(one(c) for _, c in targets))
        return {name: res for (name, _), res in zip(targets, results, strict=True)}

    @mcp.tool(annotations=READ_ONLY)
    async def get_logs(
        service: ServiceOpt = None,
        level: Literal["error", "warn", "info"] = "error",
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> dict[str, Any]:
        """Latest log entries at the given level (default: errors).

        Examples: "Show me Sonarr's recent errors", "Why is Radarr failing? check the logs"
        """
        async def one(name: str, client: Any) -> Any:
            page = await client.logs(limit, level=level)
            items = [
                fmt.drop_none(
                    {
                        "time": r.get("time"),
                        "level": r.get("level"),
                        "logger": r.get("logger"),
                        "message": fmt.shorten(r.get("message"), 400),
                        "exception": fmt.shorten(r.get("exception"), 300),
                    }
                )
                for r in page.get("records") or []
            ]
            return fmt.limited(items, limit, total=page.get("totalRecords"))

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_disk_space(service: ServiceOpt = None) -> dict[str, Any]:
        """Free and total space of the disks/volumes seen by Sonarr/Radarr.

        Examples: "How much disk space is left on the NAS?"
        """
        async def one(name: str, client: Any) -> Any:
            disks = await client.disk_space()
            return [
                fmt.drop_none(
                    {
                        "path": d.get("path"),
                        "label": d.get("label") or None,
                        "free": fmt.human_size(d.get("freeSpace")),
                        "total": fmt.human_size(d.get("totalSpace")),
                        "free_percent": round(100 * d["freeSpace"] / d["totalSpace"], 1)
                        if d.get("totalSpace")
                        else None,
                    }
                )
                for d in disks
            ]

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_command_status(service: ServiceReq, command_id: int) -> dict[str, Any]:
        """Status of an asynchronous command (search, refresh, manual import) started earlier.
        For a finished manual import it also checks that each file really reached the library.

        Examples: "Has the search for S03E04 finished?", "Did the manual import work?"
        """
        client = svc.arrs(service)[0][1]
        status = await client.command_status(command_id)
        files = (status.get("body") or {}).get("files") or []
        if (status.get("name") or status.get("commandName")) == "ManualImport" and files:
            # Finished imports are verified file by file (the command status alone lies).
            if status.get("status") not in ("queued", "started"):
                return {"service": service, **await verify_import(client, service, status, import_targets(files))}
            return {**fmt.command_summary(status), "note": t("import_still_running")}
        return fmt.command_summary(status)

    @mcp.tool(annotations=READ_ONLY)
    async def find_orphan_downloads(
        service: ServiceOpt = None,
        folder: Annotated[
            str | None,
            Field(description="Folder to scan as seen by Sonarr/Radarr; default ARR_DOWNLOADS_PATH or auto-detected"),
        ] = None,
        limit: Limit = fmt.DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Importable files in the downloads folder that no queue item is tracking
        (e.g. Download Station removed the task before Sonarr imported it).
        Groups them by series/movie and says whether each episode/movie already has
        a file (duplicate) or is missing. Also flags several files for the same episode.
        If no folder is configured, the download folders are detected from the queue and the
        import history. The scan can take a while on a NAS.

        Examples: "Why wasn't S03E04 of The Capture imported?", "Is anything stuck in /downloads?"
        """
        configured = folder or svc.settings.arr_downloads_path
        timeout = max(svc.settings.arr_timeout, _SCAN_TIMEOUT)

        async def one(name: str, client: Any) -> dict[str, Any]:
            queue = (await client.queue()).get("records") or []
            if configured:
                folders, source = [configured], "parameter" if folder else "ARR_DOWNLOADS_PATH"
            else:
                since = (datetime.now(UTC) - timedelta(days=60)).isoformat()
                history = await client.history_since(since, _EVENT_MAP[name]["imported"])
                folders, source = detect_download_folders(queue, history), "detected"
                if not folders:
                    raise ArrError(t("no_download_folder", svc=client.display_name))
            scans = await asyncio.gather(
                *(client.manual_import_scan(f, filter_existing=True, timeout=timeout) for f in folders)
            )
            seen: set[str] = set()
            merged = []
            for item in (i for scan in scans for i in scan):
                key = paths.normalize(item.get("path") or "")
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            return {"folders": folders, "folders_source": source, **_orphans(name, merged, queue, limit)}

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def find_suspicious_releases(
        service: ServiceOpt = None,
        days: Annotated[int, Field(ge=1, le=365, description="How far back to look in history")] = 30,
    ) -> dict[str, Any]:
        """Detect fake/malicious releases, with the indexer that provided them:
        executables (.exe .scr .lnk .bat .cmd .msi .zipx) in the queue, history and blocklist;
        grabs made more than a day before the episode aired or the movie's digital/physical
        release (likely="fake" if they never imported, "early_release" if they did, e.g. box
        sets); and different downloads for different episodes with the exact same size.

        Examples: "Is there any .exe in the queue?", "Which indexer is sending me fake releases?"
        """
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        by_indexer: Counter[str] = Counter()

        async def one(name: str, client: Any) -> dict[str, Any]:
            queue, history, blocklist = await asyncio.gather(
                client.queue(), client.history_since(since), client.blocklist(200)
            )
            grab_indexer = {
                h.get("downloadId"): (h.get("data") or {}).get("indexer")
                for h in history
                if h.get("eventType") == "grabbed" and h.get("downloadId")
            }

            # One count per download, even if it shows up in queue and history.
            seen_downloads: set[str] = set()
            q_hits = []
            for group in fmt.group_queue(queue.get("records") or []):
                q = group[0]
                msgs = fmt.status_messages(q) or []
                exts = find_suspicious_extensions(
                    q.get("outputPath"), q.get("errorMessage"), *msgs, titles=(q.get("title"),)
                )
                if exts:
                    item = fmt.queue_items(group, name)[0]
                    item["suspicious_extensions"] = exts
                    item["indexer"] = item.get("indexer") or grab_indexer.get(q.get("downloadId")) or "unknown"
                    by_indexer[item["indexer"]] += 1
                    seen_downloads.add(q.get("downloadId") or f"q{q.get('id')}")
                    q_hits.append(item)

            h_hits = []
            for h in history:
                data = h.get("data") or {}
                exts = find_suspicious_extensions(
                    data.get("message"), data.get("droppedPath"), data.get("importedPath"), titles=(h.get("sourceTitle"),)
                )
                if not exts:
                    continue
                item = fmt.history_item(h, name)
                item["suspicious_extensions"] = exts
                item["indexer"] = data.get("indexer") or grab_indexer.get(h.get("downloadId")) or "unknown"
                key = h.get("downloadId") or f"h{h.get('id')}"
                if key not in seen_downloads:
                    by_indexer[item["indexer"]] += 1
                    seen_downloads.add(key)
                h_hits.append(item)

            b_hits = []
            for b in blocklist.get("records") or []:
                exts = find_suspicious_extensions(b.get("message"), titles=(b.get("sourceTitle"),))
                if exts:
                    item = fmt.blocklist_item(b, name)
                    item["suspicious_extensions"] = exts
                    b_hits.append(item)

            pre = _pre_release_grabs(name, history)
            same = _identical_sizes(history)
            return fmt.drop_none(
                {
                    "queue": q_hits,
                    "history": h_hits,
                    "blocklist": b_hits,
                    "pre_release_grabs": pre or None,
                    # Only the likely fakes: an early release that imported is not the indexer's fault.
                    "likely_fakes_by_indexer": dict(
                        Counter(p["indexer"] for p in pre if p["likely"] == "fake").most_common()
                    ) or None,
                    "identical_size_grabs": same or None,
                }
            )

        out: dict[str, Any] = {"extensions": list(SUSPICIOUS_EXTENSIONS), "days": days}
        out.update(await per_service(svc, service, one))
        out["by_indexer"] = dict(by_indexer.most_common())
        if any(isinstance(out.get(n), dict) and out[n].get("queue") for n in ("sonarr", "radarr")):
            out["hint"] = t("remove_hint")
        return out


#: Some services publish a few hours before the official air time: allow a day.
PRE_RELEASE_SLACK = timedelta(hours=24)


def _released_at(service: str, h: dict[str, Any]) -> datetime | None:
    """When the grabbed item became available: air date, or a movie's digital/physical release."""
    if service == "sonarr":
        return _iso((h.get("episode") or {}).get("airDateUtc"))
    movie = h.get("movie") or {}
    dates = [d for d in (_iso(movie.get("digitalRelease")), _iso(movie.get("physicalRelease"))) if d]
    return min(dates) if dates else None


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_IMPORTED_EVENTS = ("downloadFolderImported", "seriesFolderImported", "movieFolderImported")


def _pre_release_grabs(service: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grabs made well before the listed release date, with what happened to them.

    Not every early release is fake: some services drop a whole season at once
    (box sets), earlier than the per-episode air dates. What tells them apart is the
    outcome: a fake never imports (no real video, or an executable), a real early
    release imports normally.
    """
    outcome: dict[str, str] = {}
    for h in history:
        did, ev = h.get("downloadId"), h.get("eventType")
        if did and ev in _IMPORTED_EVENTS:
            outcome[did] = "imported"
        elif did and ev == "downloadFailed":
            outcome.setdefault(did, "failed")
    hits = []
    for h in history:
        if h.get("eventType") != "grabbed":
            continue
        grabbed, released = _iso(h.get("date")), _released_at(service, h)
        if not grabbed or not released or grabbed >= released - PRE_RELEASE_SLACK:
            continue
        item = fmt.history_item(h, service)
        item["released"] = released.isoformat()
        item["days_before_release"] = round((released - grabbed).total_seconds() / 86400, 1)
        item["indexer"] = item.get("indexer") or "unknown"
        item["outcome"] = outcome.get(h.get("downloadId") or "", "not_imported")
        item["likely"] = "early_release" if item["outcome"] == "imported" else "fake"
        hits.append(item)
    hits.sort(key=lambda x: (x["likely"] != "fake", x.get("date", "")))
    return hits


def _identical_sizes(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Different downloads, for different episodes, with the very same byte size: typical
    of fake uploads. A season pack is one download recorded once per episode with the
    pack's size, so it only counts when the same size shows up in separate downloads."""
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for h in history:
        size = str((h.get("data") or {}).get("size") or "")
        if h.get("eventType") == "grabbed" and size.isdigit() and int(size) > 0:
            groups[(h.get("seriesId"), size)].append(h)
    out = []
    for (_series, size), hs in groups.items():
        episodes = {h.get("episodeId") for h in hs if h.get("episodeId")}
        downloads = {h.get("downloadId") or f"h{h.get('id')}" for h in hs}
        if len(episodes) < 2 or len(downloads) < 2:
            continue
        out.append(
            fmt.drop_none(
                {
                    "size": fmt.human_size(int(size)),
                    "series": ((hs[0].get("series") or {}).get("title")),
                    "episodes": sorted(
                        {fmt.episode_code((h.get("episode") or {}).get("seasonNumber"), (h.get("episode") or {}).get("episodeNumber")) or "?" for h in hs}
                    ),
                    "indexers": sorted({(h.get("data") or {}).get("indexer") or "unknown" for h in hs}),
                    "titles": sorted({str(h["sourceTitle"]) for h in hs if h.get("sourceTitle")})[:5],
                }
            )
        )
    return out


def detect_download_folders(
    queue: list[dict[str, Any]], history: list[dict[str, Any]], max_folders: int = 3
) -> list[str]:
    """Guess the download client's folders (as Sonarr/Radarr see them).

    - A queue item's ``outputPath`` is the release folder (or file): its parent is
      the download folder.
    - An import's ``droppedPath`` is the imported file: its parent is the download
      folder, or the release folder when it is named after the release.
    """
    counts: Counter[str] = Counter()
    original: dict[str, str] = {}

    def add(folder: str) -> None:
        if folder:
            key = paths.normalize(folder)
            counts[key] += 1
            original.setdefault(key, folder)

    for q in queue:
        if q.get("outputPath"):
            add(paths.parent(q["outputPath"]))
    for h in history:
        dropped = (h.get("data") or {}).get("droppedPath")
        if not dropped:
            continue
        folder = paths.parent(dropped)
        title = (h.get("sourceTitle") or "").casefold()
        name = paths.basename(folder).casefold()
        if title and name and (name == title or title.startswith(name) or name.startswith(title)):
            folder = paths.parent(folder)
        add(folder)

    chosen: list[str] = []
    for key, _ in counts.most_common():
        # Scanning a folder already covers its subfolders.
        if any(paths.is_within(key, c) for c in chosen):
            continue
        chosen = [c for c in chosen if not paths.is_within(c, key)] + [key]
        if len(chosen) >= max_folders:
            break
    return [original[c] for c in chosen]


def _orphans(
    service: str, scan: list[dict[str, Any]], queue: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    tracked_ids = {q.get("downloadId") for q in queue if q.get("downloadId")}
    tracked_paths = [q["outputPath"] for q in queue if q.get("outputPath")]

    def is_tracked(item: dict[str, Any]) -> bool:
        if item.get("downloadId") and item["downloadId"] in tracked_ids:
            return True
        path = item.get("path") or ""
        return any(paths.is_within(path, p) for p in tracked_paths)

    groups: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    files_per_episode: dict[int, list[str]] = defaultdict(list)
    tracked_count = 0

    for item in scan:
        if is_tracked(item):
            tracked_count += 1
            continue
        file_info = fmt.drop_none(
            {
                "path": item.get("path"),
                "size": fmt.human_size(item.get("size")),
                "quality": fmt.quality_name(item.get("quality")),
                "release_group": item.get("releaseGroup"),
                "rejections": fmt.rejections(item),
            }
        )
        if service == "sonarr":
            series = item.get("series")
            episodes = item.get("episodes") or []
            if not series or not episodes:
                unmatched.append(file_info)
                continue
            eps = []
            for e in episodes:
                eps.append(
                    {
                        "episode_id": e.get("id"),
                        "code": fmt.episode_code(e.get("seasonNumber"), e.get("episodeNumber")),
                        "already_has_file": bool(e.get("hasFile")),
                    }
                )
                if e.get("id") is not None:
                    files_per_episode[e["id"]].append(item.get("path") or "")
            file_info["episodes"] = eps
            file_info["status"] = (
                "duplicate"
                if all(e["already_has_file"] for e in eps)
                else "missing"
                if not any(e["already_has_file"] for e in eps)
                else "partial"
            )
            key = f"{series.get('title')} (id {series.get('id')})"
            g = groups.setdefault(key, {"series_id": series.get("id"), "series": series.get("title"), "files": []})
        else:
            movie = item.get("movie")
            if not movie:
                unmatched.append(file_info)
                continue
            file_info["status"] = "duplicate" if movie.get("hasFile") else "missing"
            key = f"{movie.get('title')} ({movie.get('year')})"
            g = groups.setdefault(
                key, {"movie_id": movie.get("id"), "movie": movie.get("title"), "year": movie.get("year"), "files": []}
            )
        g["files"].append(file_info)

    if service == "radarr":
        for g in groups.values():
            if len(g["files"]) > 1:
                g["conflict"] = t("movie_multiple_files")

    conflicts = [
        {"episode_id": eid, "files": paths} for eid, paths in files_per_episode.items() if len(paths) > 1
    ]
    group_list = sorted(groups.values(), key=lambda g: str(g.get("series") or g.get("movie")))
    status_counts = Counter(f["status"] for g in group_list for f in g["files"])
    return fmt.drop_none(
        {
            "scanned_files": len(scan),
            "tracked_by_queue": tracked_count,
            "orphans_by_status": dict(status_counts),
            "groups": fmt.limited(group_list, limit),
            "episode_conflicts": conflicts or None,
            "unmatched": fmt.limited(unmatched, min(limit, 20)) if unmatched else None,
        }
    )
