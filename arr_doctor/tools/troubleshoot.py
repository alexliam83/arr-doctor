"""Troubleshooting tools for the most common Sonarr/Radarr questions.

- "Why didn't it grab X?"           -> explain_search (+ grab_release)
- "Why isn't it importing?"         -> diagnose_import, check_paths
- "My download is stuck"            -> find_stalled_downloads
- "How is this release scored?"     -> parse_release
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter, OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from arr_doctor import formatting as fmt
from arr_doctor import paths
from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t
from arr_doctor.tools.common import (
    READ_ONLY,
    WRITE,
    ServiceOpt,
    ServiceReq,
    Services,
    per_service,
    resolve_movie,
    resolve_series,
    returns_candidates,
)

# Interactive searches query every indexer and can be slow.
_SEARCH_TIMEOUT = 120.0
# GET /release hits the indexers: not read-only for the outside world.
SEARCH_ANNOTATIONS = {"readOnlyHint": True, "openWorldHint": True}

# ----------------------------------------------------------------- diagnosis

#: (rule id, regex over status messages / rejections / errors). Order = priority.
IMPORT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (key, re.compile(rx, re.IGNORECASE))
    for key, rx in [
        ("dangerous", r"executable|dangerous|\.(exe|scr|lnk|bat|cmd|msi)\b"),
        ("path_conflict", r"not a directory|(file|directory) .* already exists"),
        ("permissions", r"access to the path .* is denied|permission denied|unauthorizedaccess|read-only file system"),
        ("path_missing", r"path does not exist|not a valid local path|could not find (a part of the )?(path|directory)|remote path mapping"),
        ("unknown_match", r"unknown (series|movie)|matched (to|by) (series|movie) by id|manual import required|unable to identify|unable to parse|does not match"),
        ("not_upgrade", r"not an upgrade|not a custom format upgrade|not a quality revision upgrade|existing file.*(better|cutoff)"),
        ("partial_pack", r"one or more episodes expected|not imported or missing|missing from the release"),
        ("sample", r"\bsample\b"),
        ("corrupt", r"runtime of 0|invalid video|corrupt|mediainfo"),
        ("no_files", r"no files found are eligible|no video files"),
        ("unpacking", r"unpack|\.rar\b|\barchive\b"),
        ("locked", r"locked|being used by another process"),
        ("disk_space", r"not enough (free )?(disk )?space"),
    ]
]

#: Default age before a download with no progress/activity counts as stalled.
STALL_HOURS = 6.0

STALLED_RE = re.compile(r"stalled|no connections|no seeds|metadata", re.IGNORECASE)


def diagnose(texts: list[str]) -> list[str]:
    """Rule ids matching any of the given messages, in priority order."""
    joined = "\n".join(texts)
    return [key for key, rx in IMPORT_RULES if rx.search(joined)]


def _cause(key: str, **kw: Any) -> dict[str, str]:
    return {"cause": key, "explanation": t(f"diag_{key}", **kw), "fix": t(f"fix_{key}", **kw)}


# ------------------------------------------------------------------ releases


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _reason_key(rejection: str) -> str:
    """Group rejections that differ only in numbers ("Release is 5.2 GB…" / "…7.1 GB…")."""
    return _NUM.sub("#", rejection.strip())


def release_summary(r: dict[str, Any]) -> dict[str, Any]:
    return fmt.drop_none(
        {
            "guid": r.get("guid"),
            # Sonarr/Radarr's indexer id (what grab_release needs); Prowlarr numbers them differently.
            "indexer_id": r.get("indexerId"),
            "indexer": r.get("indexer"),
            "title": r.get("title"),
            "quality": fmt.quality_name(r.get("quality")),
            "size": fmt.human_size(r.get("size")),
            "languages": fmt.language_names(r.get("languages")),
            "custom_formats": [cf.get("name") for cf in r.get("customFormats") or [] if cf.get("name")] or None,
            "cf_score": r.get("customFormatScore"),
            "protocol": r.get("protocol"),
            "seeders": r.get("seeders"),
            "leechers": r.get("leechers"),
            "age_days": r.get("age"),
            "full_season": r.get("fullSeason") or None,
            "approved": r.get("approved"),
            "temporarily_rejected": r.get("temporarilyRejected") or None,
            "rejections": r.get("rejections") or None,
        }
    )


# Rejections that only mean "this result is for something else" (another episode,
# season or series). They are noise when explaining why the wanted item failed.
OTHER_ITEM_RE = re.compile(
    r"wasn't requested|was not requested|wrong (episode|season)|unknown (series|movie)|"
    r"does not match|doesn't match|not the requested",
    re.IGNORECASE,
)


def _for_other_item(r: dict[str, Any]) -> bool:
    rejections = r.get("rejections") or []
    return bool(rejections) and any(OTHER_ITEM_RE.search(x) for x in rejections)


def summarize_releases(releases: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    approved = [r for r in releases if r.get("approved")]
    rejected = [r for r in releases if not r.get("approved")]
    other = [r for r in rejected if _for_other_item(r)]
    relevant = [r for r in rejected if not _for_other_item(r)]
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for r in relevant:
        for rej in r.get("rejections") or ["?"]:
            g = groups.setdefault(_reason_key(rej), {"reason": rej, "releases": 0})
            g["releases"] += 1
    reasons = sorted(groups.values(), key=lambda g: g["releases"], reverse=True)
    if other:
        reasons.append({"reason": t("other_item_results"), "releases": len(other)})
    by_indexer = Counter(r.get("indexer") or "?" for r in releases)
    return {
        "total": len(releases),
        "approved": len(approved),
        "rejected": len(rejected),
        "rejection_reasons": reasons,
        "by_indexer": dict(by_indexer.most_common()),
        # Sonarr/Radarr already return releases in their preference order.
        "best_approved": [release_summary(r) for r in approved[:limit]],
        "closest_rejected": [release_summary(r) for r in _closest_rejected(relevant)[:limit]],
    }


def _closest_rejected(rejected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rejected releases with the fewest (permanent) rejections first: the near misses."""
    return sorted(
        rejected, key=lambda r: (not r.get("temporarilyRejected"), len(r.get("rejections") or []))
    )


# ------------------------------------------------------------- quality rank


def quality_ranks(profile: dict[str, Any]) -> tuple[dict[int, int], set[int]]:
    """Map quality id -> rank (higher is better) and the set of allowed ids.

    Profile ``items`` are ordered worst to best; groups share one rank.
    """
    ranks: dict[int, int] = {}
    allowed: set[int] = set()
    for rank, item in enumerate(profile.get("items") or []):
        members = item.get("items") or [item]
        for member in members:
            q = member.get("quality") or {}
            if q.get("id") is None:
                continue
            ranks[q["id"]] = rank
            if item.get("allowed"):
                allowed.add(q["id"])
        if item.get("id") is not None and item.get("items"):  # group id is used as cutoff
            ranks[item["id"]] = rank
    return ranks, allowed


def upgrade_verdict(
    profile: dict[str, Any], new_quality_id: int | None, new_score: int, old_quality_id: int | None, old_score: int | None
) -> dict[str, Any]:
    ranks, allowed = quality_ranks(profile)
    min_score = profile.get("minFormatScore") or 0
    if new_quality_id is not None and allowed and new_quality_id not in allowed:
        return {"verdict": "rejected", "reason": t("verdict_quality_not_allowed")}
    if new_score < min_score:
        return {"verdict": "rejected", "reason": t("verdict_below_min_score", score=new_score, min=min_score)}
    if old_quality_id is None:
        return {"verdict": "wanted", "reason": t("verdict_no_file")}
    if not profile.get("upgradeAllowed", True):
        return {"verdict": "not_upgrade", "reason": t("verdict_upgrades_disabled")}
    new_rank, old_rank = ranks.get(new_quality_id or -1, -1), ranks.get(old_quality_id, -1)
    cutoff_rank = ranks.get(profile.get("cutoff", -1), 10**6)
    cutoff_score = profile.get("cutoffFormatScore")
    old_score = old_score or 0
    if new_rank > old_rank:
        if old_rank >= cutoff_rank:
            return {"verdict": "not_upgrade", "reason": t("verdict_cutoff_met")}
        return {"verdict": "upgrade", "reason": t("verdict_better_quality")}
    if new_rank < old_rank:
        return {"verdict": "not_upgrade", "reason": t("verdict_worse_quality")}
    if cutoff_score is not None and old_score >= cutoff_score:
        return {"verdict": "not_upgrade", "reason": t("verdict_score_cutoff_met", cutoff=cutoff_score)}
    min_step = profile.get("minUpgradeFormatScore") or 1
    if new_score - old_score >= min_step:
        return {"verdict": "upgrade", "reason": t("verdict_better_score", new=new_score, old=old_score)}
    return {"verdict": "not_upgrade", "reason": t("verdict_same_or_lower_score", new=new_score, old=old_score)}


# ------------------------------------------------------------------ register


def register(mcp: FastMCP, svc: Services, readonly: bool) -> None:
    @mcp.tool(annotations=SEARCH_ANNOTATIONS)
    @returns_candidates
    async def explain_search(
        series: Annotated[str | int | None, Field(description="Sonarr series ID or title")] = None,
        season: Annotated[int | None, Field(description="Season number")] = None,
        episode: Annotated[int | None, Field(description="Episode number within `season`; omit to search the whole season")] = None,
        movie: Annotated[str | int | None, Field(description="Radarr movie ID or title")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 5,
    ) -> dict[str, Any]:
        """Explain why Sonarr/Radarr did not grab something: run an interactive search and
        summarize every release found, grouped by rejection reason (language, size, quality,
        custom format score, already have it…), plus basic checks (monitored, aired, available).
        The guids returned can be grabbed with grab_release. Queries every indexer live, so it
        counts against the hourly indexer budget: use it for one item at a time, never in a loop.

        Examples: "Why didn't Sonarr grab S03E04 of The Capture?",
        "Why is Dune not downloading? What releases are out there?"
        """
        timeout = max(svc.settings.arr_timeout, _SEARCH_TIMEOUT)
        if series is None and movie is None:
            raise ArrError(t("need_series_or_movie"))
        if series is not None and season is None:
            raise ArrError(t("need_season"))
        checks: list[str] = []
        if movie is not None:
            radarr = svc.require_radarr()
            m = await resolve_movie(radarr, movie)
            if not m.get("monitored"):
                checks.append(t("check_movie_unmonitored"))
            if not m.get("isAvailable"):
                checks.append(t("check_movie_not_available", availability=m.get("minimumAvailability")))
            if m.get("hasFile"):
                checks.append(t("check_has_file"))
            svc.budget.consume(1)  # only once the target is known: typos don't spend budget
            releases = await radarr.releases(m["id"], timeout=timeout)
            target = {"service": "radarr", "movie": f"{m.get('title')} ({m.get('year')})", "movie_id": m["id"]}
        elif series is not None:
            if season is None:
                raise ArrError(t("need_season"))
            sonarr = svc.require_sonarr()
            s = await resolve_series(sonarr, series)
            if not s.get("monitored"):
                checks.append(t("check_series_unmonitored"))
            season_info = next((x for x in s.get("seasons") or [] if x.get("seasonNumber") == season), None)
            if season_info is None:
                raise ArrError(t("no_such_season", title=s.get("title"), season=season))
            if not season_info.get("monitored"):
                checks.append(t("check_season_unmonitored", season=season))
            if s.get("seriesType") in ("anime", "daily"):
                checks.append(t("check_series_type", type=s.get("seriesType")))
            target = {"service": "sonarr", "series": s.get("title"), "series_id": s["id"], "season": season}
            if episode is not None:
                eps = await sonarr.get_episodes(s["id"], season)
                ep = next((e for e in eps if e.get("episodeNumber") == episode), None)
                if ep is None:
                    raise ArrError(t("episodes_not_in_season", title=s.get("title"), missing=[episode], season=season))
                if not ep.get("monitored"):
                    checks.append(t("check_episode_unmonitored"))
                if (ep.get("airDateUtc") or "") > datetime.now(UTC).isoformat():
                    checks.append(t("check_not_aired", date=ep.get("airDateUtc")))
                if ep.get("hasFile"):
                    checks.append(t("check_has_file"))
                target.update(episode=fmt.episode_code(season, episode), episode_id=ep["id"])
                svc.budget.consume(1)
                releases = await sonarr.releases(episode_id=ep["id"], timeout=timeout)
            else:
                svc.budget.consume(1)
                releases = await sonarr.releases(series_id=s["id"], season=season, timeout=timeout)
        else:
            raise ArrError(t("need_series_or_movie"))

        summary = summarize_releases(releases, limit)
        # Remember it: Sonarr/Radarr count this as the item's last search, and a follow-up
        # search_* call should point to these results instead of searching again.
        key = ("radarr", target["movie_id"]) if "movie_id" in target else ("sonarr", target.get("episode_id", -1))
        svc.interactive[key] = (time.monotonic(), summary["approved"])
        if not releases:
            checks.append(t("check_no_results"))
        elif not summary["approved"]:
            checks.append(t("check_none_approved"))
        return fmt.drop_none({**target, "checks": checks, **summary, "note": t("grab_note") if releases else None})

    @mcp.tool(annotations=READ_ONLY)
    async def diagnose_import(
        service: ServiceReq,
        queue_id: Annotated[int | None, Field(description="Queue item ID (from get_queue); omit to check every stuck item")] = None,
    ) -> dict[str, Any]:
        """Diagnose why a download is not being imported: combines the queue status messages,
        Sonarr/Radarr's own rejections for the files in the download, and path visibility,
        and returns the probable cause with a concrete fix (remote path mapping, permissions,
        manual match, not an upgrade, sample, fake release…).

        Examples: "Why isn't S03E04 importing?", "Why is everything stuck in importBlocked?"
        """
        client = svc.arrs(service)[0][1]
        page = await client.queue()
        records = page.get("records") or []
        # One diagnosis per download: a season pack has one queue record per episode.
        groups = fmt.group_queue(records)
        if queue_id is not None:
            groups = [g for g in groups if any(q.get("id") == queue_id for q in g)]
            if not groups:
                raise ArrError(t("queue_item_not_found", id=queue_id))
        else:
            groups = [
                g
                for g in groups
                if g[0].get("trackedDownloadState") in ("importBlocked", "importPending", "failedPending")
                or g[0].get("trackedDownloadStatus") in ("warning", "error")
            ][:10]
        timeout = max(svc.settings.arr_timeout, 60.0)
        results = await asyncio.gather(*(_diagnose_one(client, service, g, timeout) for g in groups))
        return {"service": service, "checked": len(results), "items": list(results)}

    @mcp.tool(annotations=READ_ONLY)
    async def check_paths(service: ServiceOpt = None) -> dict[str, Any]:
        """Check the path setup that breaks most imports: root folders (accessible, free space),
        remote path mappings, download clients, whether Sonarr/Radarr can actually see the
        download clients' output folders, and the related health warnings.

        Examples: "Is my remote path mapping right?", "Why does Sonarr say the path does not exist?"
        """

        async def one(name: str, client: Any) -> dict[str, Any]:
            roots, mappings, clients, queue, health = await asyncio.gather(
                client.root_folders(), client.remote_path_mappings(), client.download_clients(),
                client.queue(), client.health(),
            )
            outputs = _output_dirs(queue.get("records") or [])
            scans = await asyncio.gather(
                *(client.manual_import_scan(d, filter_existing=False, timeout=max(svc.settings.arr_timeout, 60.0)) for d in outputs),
                return_exceptions=True,
            )
            visibility = []
            problems = []
            for d, scan in zip(outputs, scans, strict=True):
                visible = isinstance(scan, list) and len(scan) > 0
                visibility.append({"path": d, "visible": visible})
                if not visible:
                    problems.append(_cause("path_not_visible", path=d))
            for r in roots:
                if not r.get("accessible", True):
                    problems.append(_cause("root_inaccessible", path=r.get("path")))
            path_health = [
                fmt.drop_none({"source": h.get("source"), "type": h.get("type"), "message": h.get("message"), "wiki": h.get("wikiUrl")})
                for h in health
                if re.search(r"path|folder|mapping|import|downloadclient", str(h.get("source")) + str(h.get("message")), re.I)
            ]
            return fmt.drop_none(
                {
                    "root_folders": [
                        fmt.drop_none({"path": r.get("path"), "accessible": r.get("accessible"), "free": fmt.human_size(r.get("freeSpace"))})
                        for r in roots
                    ],
                    "remote_path_mappings": [
                        {"host": m.get("host"), "remote_path": m.get("remotePath"), "local_path": m.get("localPath")}
                        for m in mappings
                    ],
                    "download_clients": [_download_client(c) for c in clients],
                    "download_output_folders": visibility,
                    "health": path_health,
                    "problems": problems,
                    "ok": not problems and not path_health,
                }
            )

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def find_stalled_downloads(
        service: ServiceOpt = None,
        min_hours: Annotated[float, Field(ge=0, description="Ignore items added less than N hours ago (no-progress check)")] = STALL_HOURS,
    ) -> dict[str, Any]:
        """Find downloads that are stuck: reported as stalled / no connections / no seeds by the
        download client, with a download client error, or — after `min_hours` — still at 0 %
        (no_progress), downloading with no speed/ETA (no_activity), or with no metadata yet
        (size 0, typical of magnets without peers). Paused or queued items are not reported.
        Pair with remove_from_queue(blocklist=true) to grab a different release.

        Examples: "Which downloads are stalled?", "Remove the stuck torrents and find another release"
        """
        now = datetime.now(UTC)

        async def one(name: str, client: Any) -> dict[str, Any]:
            records = (await client.queue()).get("records") or []
            # Some clients (e.g. Download Station before metadata) report no "added" date:
            # fall back to when Sonarr/Radarr grabbed it.
            grabbed: dict[str, str] = {}
            if any(not q.get("added") for q in records):
                since = (now - timedelta(days=90)).isoformat()
                for h in await client.history_since(since, 1):  # 1 = grabbed in Sonarr and Radarr
                    if h.get("downloadId") and h.get("date"):
                        grabbed.setdefault(h["downloadId"], h["date"])
            stalled = []
            for group in fmt.group_queue(records):
                q = group[0]
                added = parse_date(q.get("added") or grabbed.get(q.get("downloadId") or ""))
                reason = stall_reason(q, now, min_hours, added)
                if reason:
                    item = fmt.queue_items(group, name)[0]
                    item["stall_reason"] = reason
                    size, left = q.get("size") or 0, q.get("sizeleft") or 0
                    # Floor, so 99.96 % is never shown as a misleading 100 %.
                    item["progress_percent"] = math.floor(1000 * (size - left) / size) / 10 if size else 0.0
                    if added:
                        item["age_hours"] = round((now - added).total_seconds() / 3600, 1)
                    stalled.append(item)
            return {"stalled": stalled}

        out = await per_service(svc, service, one)
        if any(isinstance(v, dict) and v.get("stalled") for v in out.values()):
            out["hint"] = t("stalled_hint")
        return out

    @mcp.tool(annotations=READ_ONLY)
    async def parse_release(
        title: Annotated[str, Field(description="Release name, e.g. 'The.Capture.S03E04.1080p.WEB.H264-NTb'")],
        service: ServiceOpt = None,
    ) -> dict[str, Any]:
        """Show how Sonarr/Radarr interpret a release name: matched series/episodes or movie,
        quality, languages, custom formats and score. If the item already has a file, compares
        both and estimates whether it would be an upgrade under the quality profile and why.

        Examples: "How would Sonarr score 'The.Capture.S03E04.2160p.WEB.DV-GRP'?",
        "Why is this release 'not an upgrade'?"
        """
        if service is None:
            service = "radarr" if svc.radarr and not svc.sonarr else "sonarr"
            if svc.sonarr and svc.radarr and not re.search(r"\bS\d{1,2}E\d{1,3}|\bS\d{1,2}\b|\d{1,2}x\d{2}", title, re.I):
                service = "radarr"
        client = svc.arrs(service)[0][1]
        parsed = await client.parse(title)
        if service == "sonarr":
            return await _parse_sonarr(svc, parsed)
        return await _parse_radarr(svc, parsed)

    if readonly:
        return

    @mcp.tool(annotations=WRITE)
    async def grab_release(
        service: ServiceReq,
        guid: Annotated[str, Field(description="Release guid from explain_search")],
        indexer_id: Annotated[int, Field(description="indexer_id from explain_search (Sonarr/Radarr's id, not Prowlarr's)")],
    ) -> dict[str, Any]:
        """Send a specific release (from explain_search) to the download client, even if it
        was rejected. Only works within ~30 minutes of the search; search again if it fails.

        Examples: "Grab that 1080p release anyway", "Download the second one from the list"
        """
        client = svc.arrs(service)[0][1]
        svc.budget.consume(1)
        result = await client.grab_release(guid, indexer_id)
        return {"grabbed": True, "service": service, "release": release_summary(result or {"guid": guid})}


# ------------------------------------------------------------------ helpers


async def _diagnose_one(client: Any, service: str, group: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    q = group[0]
    item = fmt.queue_items(group, service)[0]
    texts = (fmt.status_messages(q) or []) + ([q["errorMessage"]] if q.get("errorMessage") else [])
    state = q.get("trackedDownloadState")
    files: list[dict[str, Any]] = []
    scan_error = None
    if q.get("downloadId") and state not in ("downloading",):
        try:
            scan = await client.manual_import_for_download(q["downloadId"], timeout=timeout)
        except ArrError as exc:
            scan, scan_error = [], str(exc)
        for f in scan:
            rej = fmt.rejections(f)
            texts.extend(rej or [])
            files.append(fmt.drop_none({"path": f.get("path"), "quality": fmt.quality_name(f.get("quality")), "rejections": rej}))
    else:
        scan = None

    keys = diagnose(texts)
    if "partial_pack" in keys and files and any(f.get("rejections") for f in files):
        # Sonarr adds "One or more episodes … were not imported" whenever nothing got in;
        # if the files are there and each has its own rejection, nothing is missing.
        keys.remove("partial_pack")
    causes = [_cause(key) for key in keys]
    if state == "downloading" or q.get("status") in ("downloading", "queued", "paused", "delay"):
        causes.append(_cause("still_downloading"))
    elif scan == [] and q.get("outputPath") and not any(c["cause"] == "dangerous" for c in causes):
        causes.insert(0, _cause("path_not_visible", path=q.get("outputPath")))
    if not causes:
        causes.append(_cause("unknown"))
    return fmt.drop_none({**item, "files": files or None, "scan_error": scan_error, "diagnosis": causes})


def _output_dirs(records: list[dict[str, Any]], max_dirs: int = 5) -> list[str]:
    """Distinct parent folders of completed downloads' output paths."""
    seen: OrderedDict[str, None] = OrderedDict()
    for q in records:
        out = q.get("outputPath")
        if not out or q.get("status") not in ("completed", "warning"):
            continue
        seen.setdefault(paths.parent(out), None)
    return list(seen)[:max_dirs]


def _download_client(c: dict[str, Any]) -> dict[str, Any]:
    fields = {f.get("name"): f.get("value") for f in c.get("fields") or [] if isinstance(f, dict)}
    return fmt.drop_none(
        {
            "name": c.get("name"),
            "type": c.get("implementationName") or c.get("implementation"),
            "enabled": c.get("enable"),
            "host": fields.get("host"),
            "port": fields.get("port"),
            "category": fields.get("tvCategory") or fields.get("movieCategory") or fields.get("category"),
            "directory": fields.get("tvDirectory") or fields.get("movieDirectory") or fields.get("directory"),
            "remove_completed": c.get("removeCompletedDownloads"),
        }
    )


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def stall_reason(q: dict[str, Any], now: datetime, min_hours: float, added: datetime | None) -> str | None:
    texts = " ".join((fmt.status_messages(q) or []) + [q.get("errorMessage") or ""])
    status = q.get("status")
    if status == "completed" or q.get("trackedDownloadState") in ("importPending", "importBlocked", "imported"):
        return None
    if STALLED_RE.search(texts):
        return "stalled"
    if status in ("failed", "downloadClientUnavailable") or (status == "warning" and texts.strip()):
        return "client_error"
    if status not in ("downloading", "warning"):
        return None  # paused, queued, delayed… are waiting on purpose
    old_enough = added is None or (now - added).total_seconds() >= min_hours * 3600
    size, left = q.get("size") or 0, q.get("sizeleft")
    if not size:
        # Nothing known about the content yet: the client never got the metadata.
        return "no_metadata" if old_enough else None
    if added is None or not old_enough:
        return None
    if left is not None and left >= size:
        return "no_progress"
    if not q.get("timeleft"):
        return "no_activity"  # downloading but no speed, so no ETA
    return None


async def _parse_sonarr(svc: Services, parsed: dict[str, Any]) -> dict[str, Any]:
    info = parsed.get("parsedEpisodeInfo") or {}
    series = parsed.get("series") or {}
    episodes = parsed.get("episodes") or []
    out: dict[str, Any] = {
        "service": "sonarr",
        "title": parsed.get("title"),
        "parsed": fmt.drop_none(
            {
                "series_title": info.get("seriesTitle"),
                "season": info.get("seasonNumber"),
                "episodes": info.get("episodeNumbers") or None,
                "full_season": info.get("fullSeason") or None,
                "quality": fmt.quality_name(info.get("quality")),
                "release_group": info.get("releaseGroup"),
                "languages": fmt.language_names(parsed.get("languages") or info.get("languages")),
            }
        ),
        "matched_series": fmt.drop_none({"id": series.get("id"), "title": series.get("title")}) or None,
        "matched_episodes": [fmt.episode_code(e.get("seasonNumber"), e.get("episodeNumber")) for e in episodes] or None,
        "custom_formats": [cf.get("name") for cf in parsed.get("customFormats") or []],
        "cf_score": parsed.get("customFormatScore", 0),
    }
    if not info:
        out["note"] = t("parse_failed")
        return fmt.drop_none(out)
    if not series:
        out["note"] = t("parse_no_series")
        return fmt.drop_none(out)

    sonarr = svc.require_sonarr()
    # includeEpisodeFile: without it the existing file is invisible and every
    # release would look like "no file yet, it would be grabbed".
    full = await sonarr.get_episodes_by_id([e["id"] for e in episodes], include_file=True) if episodes else []
    profiles = {p["id"]: p for p in await sonarr.quality_profiles()}
    profile = profiles.get(series.get("qualityProfileId")) or {}
    files: list[dict[str, Any]] = [e["episodeFile"] for e in full if e.get("episodeFile")]
    if not full:
        return fmt.drop_none(out)
    if files:
        ef = files[0]
        out["existing_file"] = fmt.drop_none(
            {
                "quality": fmt.quality_name(ef.get("quality")),
                "cf_score": ef.get("customFormatScore"),
                "custom_formats": [cf.get("name") for cf in ef.get("customFormats") or []] or None,
            }
        )
        old_q, old_s = ((ef.get("quality") or {}).get("quality") or {}).get("id"), ef.get("customFormatScore")
    else:
        old_q, old_s = None, None
    new_q = ((info.get("quality") or {}).get("quality") or {}).get("id")
    out["quality_profile"] = profile.get("name")
    out["estimate"] = upgrade_verdict(profile, new_q, out["cf_score"] or 0, old_q, old_s)
    return fmt.drop_none(out)


async def _parse_radarr(svc: Services, parsed: dict[str, Any]) -> dict[str, Any]:
    info = parsed.get("parsedMovieInfo") or {}
    movie = parsed.get("movie") or {}
    out: dict[str, Any] = {
        "service": "radarr",
        "title": parsed.get("title"),
        "parsed": fmt.drop_none(
            {
                "movie_title": info.get("primaryMovieTitle") or info.get("movieTitle"),
                "year": info.get("year") or None,
                "edition": info.get("edition") or None,
                "quality": fmt.quality_name(info.get("quality")),
                "release_group": info.get("releaseGroup"),
                "languages": fmt.language_names(parsed.get("languages") or info.get("languages")),
            }
        ),
        "matched_movie": fmt.drop_none({"id": movie.get("id"), "title": movie.get("title"), "year": movie.get("year")}) or None,
        "custom_formats": [cf.get("name") for cf in parsed.get("customFormats") or []],
        "cf_score": parsed.get("customFormatScore", 0),
    }
    if not info:
        out["note"] = t("parse_failed")
        return fmt.drop_none(out)
    if not movie.get("id"):
        out["note"] = t("parse_no_movie")
        return fmt.drop_none(out)

    radarr = svc.require_radarr()
    full, profiles = await asyncio.gather(radarr.get_movie(movie["id"]), radarr.quality_profiles())
    profile = {p["id"]: p for p in profiles}.get(full.get("qualityProfileId")) or {}
    mf = full.get("movieFile") or {}
    if mf:
        out["existing_file"] = fmt.drop_none(
            {
                "quality": fmt.quality_name(mf.get("quality")),
                "cf_score": mf.get("customFormatScore"),
                "custom_formats": [cf.get("name") for cf in mf.get("customFormats") or []] or None,
            }
        )
    old_q = ((mf.get("quality") or {}).get("quality") or {}).get("id") if mf else None
    new_q = ((info.get("quality") or {}).get("quality") or {}).get("id")
    out["quality_profile"] = profile.get("name")
    out["estimate"] = upgrade_verdict(profile, new_q, out["cf_score"] or 0, old_q, mf.get("customFormatScore") if mf else None)
    return fmt.drop_none(out)
