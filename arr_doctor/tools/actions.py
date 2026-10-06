"""Write tools: searches, monitoring, queue removal, refresh, adding and manual import.

Not registered at all when ``ARR_READONLY=true``.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from arr_doctor import formatting as fmt
from arr_doctor import paths
from arr_doctor.clients.base import ArrError
from arr_doctor.guards import recently_searched
from arr_doctor.i18n import t
from arr_doctor.tools.common import (
    DESTRUCTIVE,
    WRITE,
    ServiceOpt,
    ServiceReq,
    Services,
    normalize_title,
    per_service,
    resolve_movie,
    resolve_series,
    returns_candidates,
)
from arr_doctor.tools.importcheck import import_targets, verify_import

SeriesRef = Annotated[str | int, Field(description="Series ID or title")]
MovieRef = Annotated[str | int, Field(description="Movie ID or title")]

SeriesMonitor = Literal[
    "all", "future", "missing", "existing", "firstSeason", "lastSeason", "pilot", "recent", "none"
]
MinimumAvailability = Literal["announced", "inCinemas", "released"]


# Rejections that only say "the current file is better": the case allow_downgrade overrides.
NOT_UPGRADE_RE = re.compile(r"not an upgrade|not a custom format upgrade|not a quality revision upgrade", re.IGNORECASE)


def _plan_search(
    svc: Services,
    items: list[dict[str, Any]],
    label: Callable[[dict[str, Any]], str],
    force: bool,
    confirm: bool,
    service: str = "sonarr",
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Apply the search guardrails. Returns (items to search, early answer or None).

    - Items searched by Sonarr/Radarr less than ARR_SEARCH_COOLDOWN_MINUTES ago are
      skipped unless ``force`` (searching again so soon rarely finds anything new).
    - More than ARR_SEARCH_CONFIRM_ABOVE items need ``confirm`` (the web UI also
      warns with the count before "Search All").
    - Episodes that have not aired yet (and movies Radarr does not consider available)
      are skipped unless ``force``: before release, matching results are fakes.
    - The search counts against the hourly indexer budget.
    """
    cooldown = svc.settings.arr_search_cooldown_minutes
    unreleased = [i for i in items if not force and not_released_yet(i)]
    recent = [
        i for i in items if i not in unreleased and not force and recently_searched(i.get("lastSearchTime"), cooldown)
    ]
    todo = [i for i in items if i not in recent and i not in unreleased]
    skipped = [label(i) for i in recent] or None
    not_aired = [label(i) for i in unreleased] or None
    if not todo:
        # Searched a moment ago with explain_search and it found approved releases? Then
        # the useful next step is grabbing one of those, not "nothing new would turn up".
        approved = sum(
            hit[1]
            for i in recent
            if (hit := svc.interactive.get((service, i.get("id", -1))))
            and time.monotonic() - hit[0] < cooldown * 60
        )
        if approved:
            return todo, {"searched": False, "skipped_recently_searched": skipped, "message": t("use_explain_results", n=approved)}
        key = "all_not_released" if unreleased and not recent else "all_recently_searched"
        return todo, fmt.drop_none(
            {
                "searched": False,
                "skipped_recently_searched": skipped,
                "skipped_not_released": not_aired,
                "message": t(key, minutes=cooldown),
            }
        )
    threshold = svc.settings.arr_search_confirm_above
    if len(todo) > threshold and not confirm:
        return todo, fmt.drop_none(
            {
                "searched": False,
                "would_search": len(todo),
                "skipped_recently_searched": skipped,
                "message": t("search_confirm", n=len(todo), threshold=threshold),
            }
        )
    svc.budget.consume(1)
    return todo, None


def not_released_yet(item: dict[str, Any]) -> bool:
    """An episode whose air date is in the future, or a movie Radarr says is not available."""
    if item.get("isAvailable") is False:
        return True
    air = item.get("airDateUtc")
    return isinstance(air, str) and air > datetime.now(UTC).isoformat()


def _started(c: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = fmt.command_summary(c)
    out.update({k: v for k, v in extra.items() if v is not None})
    out["note"] = t("command_note")
    return out


def register(mcp: FastMCP, svc: Services) -> None:
    if svc.sonarr:
        _register_sonarr(mcp, svc)
    if svc.radarr:
        _register_radarr(mcp, svc)
    _register_common(mcp, svc)


# --------------------------------------------------------------------- Sonarr


def _register_sonarr(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def search_episodes(
        episode_ids: Annotated[list[int] | None, Field(description="Sonarr episode IDs")] = None,
        series: Annotated[str | int | None, Field(description="Series ID or title, with season + episodes")] = None,
        season: int | None = None,
        episodes: Annotated[list[int] | None, Field(description="Episode numbers within `season`")] = None,
        confirm: Annotated[bool, Field(description="Required when the search covers many items (shows the count first)")] = False,
        force: Annotated[bool, Field(description="Also search items Sonarr/Radarr searched very recently")] = False,
    ) -> dict[str, Any]:
        """Trigger an indexer search for specific episodes (by ID, or series + season + episode numbers).
        Episodes searched in the last hour are skipped (force=true to override) and searches over
        many episodes ask for confirmation first, to respect indexer limits.

        Examples: "Search S03E04 of The Capture again", "Look for episodes 3 and 4 of season 1 of Severance"
        """
        sonarr = svc.require_sonarr()
        targets: list[dict[str, Any]] = await sonarr.get_episodes_by_id(list(episode_ids)) if episode_ids else []
        if series is not None:
            if season is None or not episodes:
                raise ArrError(t("need_season_and_episodes"))
            s = await resolve_series(sonarr, series)
            eps = await sonarr.get_episodes(s["id"], season)
            wanted = {e["episodeNumber"]: e for e in eps if e.get("episodeNumber") in episodes}
            missing = sorted(set(episodes) - set(wanted))
            if missing:
                raise ArrError(t("episodes_not_in_season", title=s.get("title"), missing=missing, season=season))
            targets.extend(dict(wanted[n], series={"title": s.get("title")}) for n in sorted(wanted))
        if not targets:
            raise ArrError(t("need_episode_target"))

        def label(e: dict[str, Any]) -> str:
            title = (e.get("series") or {}).get("title")
            code = fmt.episode_code(e.get("seasonNumber"), e.get("episodeNumber")) or str(e.get("id"))
            return f"{title} {code}" if title else code

        todo, early = _plan_search(svc, targets, label, force, confirm)
        if early:
            return early
        ids = [e["id"] for e in todo]
        cmd = await sonarr.command("EpisodeSearch", episodeIds=ids)
        skipped = [label(e) for e in targets if e not in todo and not not_released_yet(e)] or None
        unaired = [label(e) for e in targets if e not in todo and not_released_yet(e)] or None
        return _started(
            cmd, service="sonarr", episode_ids=ids, episodes=[label(e) for e in todo],
            skipped_recently_searched=skipped, skipped_not_released=unaired,
        )

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def search_season(series: SeriesRef, season: int) -> dict[str, Any]:
        """Trigger an indexer search for a whole season (season packs or every episode).

        Examples: "Search season 2 of The Capture"
        """
        sonarr = svc.require_sonarr()
        s = await resolve_series(sonarr, series)
        svc.budget.consume(1)
        cmd = await sonarr.command("SeasonSearch", seriesId=s["id"], seasonNumber=season)
        return _started(cmd, service="sonarr", series=s.get("title"), season=season)

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def add_series(
        term: Annotated[str, Field(description="Title to look up online, or 'tvdb:12345'")],
        quality_profile: Annotated[str | int | None, Field(description="Quality profile name or ID")] = None,
        root_folder: Annotated[str | None, Field(description="Root folder path")] = None,
        tvdb_id: Annotated[int | None, Field(description="Pick this exact result from the lookup")] = None,
        monitor: SeriesMonitor = "all",
        search_now: Annotated[bool, Field(description="Search for missing episodes right away")] = True,
    ) -> dict[str, Any]:
        """Add a new series to Sonarr. Looks it up online first; if several results match it
        returns the candidates, and if quality profile or root folder are missing it returns
        the available options instead of guessing.

        Examples: "Add The Capture with the HD-1080p profile", "Add Severance and search for it"
        """
        sonarr = svc.require_sonarr()
        results = await sonarr.lookup_series(term)
        chosen = _pick_lookup(results, term, tvdb_id, "tvdbId", "tvdb_id")
        if "candidates" in chosen:
            return chosen
        item = chosen["item"]
        if item.get("id"):
            return {"added": False, "message": t("already_in_library", title=item.get("title"), svc="Sonarr", id=item["id"])}

        options = await _profile_and_folder(sonarr, quality_profile, root_folder)
        if "missing" in options:
            return {"added": False, "series": _lookup_candidate(item, "tvdbId", "tvdb_id"), **options}

        body = {
            **item,
            "qualityProfileId": options["quality_profile_id"],
            "rootFolderPath": options["root_folder"],
            "monitored": monitor != "none",
            "seasonFolder": True,
            "addOptions": {
                "monitor": monitor,
                "searchForMissingEpisodes": search_now,
                "searchForCutoffUnmetEpisodes": False,
            },
        }
        if search_now:
            svc.budget.consume(1)
        added = await sonarr.add_series(body)
        return {"added": True, "series": fmt.series_summary(added), "path": added.get("path"), "search_started": search_now}


# --------------------------------------------------------------------- Radarr


def _register_radarr(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def search_movie(
        movies: Annotated[list[str | int], Field(description="Movie IDs or titles")],
        confirm: Annotated[bool, Field(description="Required when the search covers many items (shows the count first)")] = False,
        force: Annotated[bool, Field(description="Also search items Sonarr/Radarr searched very recently")] = False,
    ) -> dict[str, Any]:
        """Trigger an indexer search for one or more movies. Movies searched in the last hour are
        skipped (force=true to override) and searches over many movies ask for confirmation first.

        Examples: "Search Dune again", "Look for a new release of Oppenheimer"
        """
        radarr = svc.require_radarr()
        resolved = [await resolve_movie(radarr, m) for m in movies]

        def label(m: dict[str, Any]) -> str:
            return f"{m.get('title')} ({m.get('year')})"

        todo, early = _plan_search(svc, resolved, label, force, confirm, service="radarr")
        if early:
            return early
        cmd = await radarr.command("MoviesSearch", movieIds=[m["id"] for m in todo])
        skipped = [label(m) for m in resolved if m not in todo and not not_released_yet(m)] or None
        unavailable = [label(m) for m in resolved if m not in todo and not_released_yet(m)] or None
        return _started(
            cmd, service="radarr", movies=[label(m) for m in todo],
            skipped_recently_searched=skipped, skipped_not_released=unavailable,
        )

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def add_movie(
        term: Annotated[str, Field(description="Title to look up online, or 'tmdb:12345' / 'imdb:tt123'")],
        quality_profile: Annotated[str | int | None, Field(description="Quality profile name or ID")] = None,
        root_folder: Annotated[str | None, Field(description="Root folder path")] = None,
        tmdb_id: Annotated[int | None, Field(description="Pick this exact result from the lookup")] = None,
        minimum_availability: MinimumAvailability = "released",
        search_now: Annotated[bool, Field(description="Search for the movie right away")] = True,
    ) -> dict[str, Any]:
        """Add a new movie to Radarr. Looks it up online first; if several results match it
        returns the candidates, and if quality profile or root folder are missing it returns
        the available options instead of guessing.

        Examples: "Add Dune Part Two in HD-1080p", "Add the movie Past Lives"
        """
        radarr = svc.require_radarr()
        results = await radarr.lookup_movie(term)
        chosen = _pick_lookup(results, term, tmdb_id, "tmdbId", "tmdb_id")
        if "candidates" in chosen:
            return chosen
        item = chosen["item"]
        if item.get("id"):
            return {"added": False, "message": t("already_in_library", title=item.get("title"), svc="Radarr", id=item["id"])}

        options = await _profile_and_folder(radarr, quality_profile, root_folder)
        if "missing" in options:
            return {"added": False, "movie": _lookup_candidate(item, "tmdbId", "tmdb_id"), **options}

        body = {
            **item,
            "qualityProfileId": options["quality_profile_id"],
            "rootFolderPath": options["root_folder"],
            "monitored": True,
            "minimumAvailability": minimum_availability,
            "addOptions": {"searchForMovie": search_now, "monitor": "movieOnly"},
        }
        if search_now:
            svc.budget.consume(1)
        added = await radarr.add_movie(body)
        return {"added": True, "movie": fmt.movie_summary(added), "path": added.get("path"), "search_started": search_now}


# ------------------------------------------------------------------- Both


def _register_common(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def search_missing(
        service: ServiceOpt = None,
        series: Annotated[str | int | None, Field(description="Limit the Sonarr search to one series")] = None,
        confirm: Annotated[bool, Field(description="Required when many items would be searched (shows the count first)")] = False,
    ) -> dict[str, Any]:
        """Trigger a search for every monitored missing episode (Sonarr) and/or movie (Radarr).
        Sonarr/Radarr normally find new releases through RSS on their own; mass searches hit
        every indexer once per item and can exceed indexer limits. Over a few items it first
        returns how many would be searched and needs confirm=true. Prefer narrower searches.

        Examples: "Search everything that's missing", "Search all missing episodes of The Capture"
        """
        if series is not None:
            service = "sonarr"
        threshold = svc.settings.arr_search_confirm_above

        async def one(name: str, client: Any) -> dict[str, Any]:
            body: dict[str, Any] = {}
            if name == "sonarr" and series is not None:
                s = await resolve_series(svc.require_sonarr(), series)
                body["seriesId"] = s["id"]
                now = datetime.now(UTC).isoformat()
                eps = await svc.require_sonarr().get_episodes(s["id"])
                count = sum(
                    1 for e in eps if e.get("monitored") and not e.get("hasFile") and (e.get("airDateUtc") or "9999") <= now
                )
            else:
                count = (await client.missing(1, monitored=True)).get("totalRecords") or 0
            if count == 0:
                return {"searched": False, "would_search": 0, "message": t("nothing_missing")}
            if count > threshold and not confirm:
                return {"searched": False, "would_search": count, "message": t("search_confirm", n=count, threshold=threshold)}
            svc.budget.consume(1)
            if name == "sonarr":
                return _started(await client.command("MissingEpisodeSearch", monitored=True, **body), items=count)
            return _started(await client.command("MissingMoviesSearch"), items=count)

        return await per_service(svc, service, one)

    @mcp.tool(annotations={**WRITE, "idempotentHint": True})
    @returns_candidates
    async def set_monitored(
        monitored: bool,
        episode_ids: Annotated[list[int] | None, Field(description="Sonarr episode IDs")] = None,
        series: Annotated[str | int | None, Field(description="Series ID or title")] = None,
        season: Annotated[int | None, Field(description="With `series`: only this season")] = None,
        episodes: Annotated[
            list[int] | None, Field(description="With `series` + `season`: only these episode numbers")
        ] = None,
        movie: Annotated[str | int | None, Field(description="Radarr movie ID or title")] = None,
    ) -> dict[str, Any]:
        """Monitor or unmonitor episodes (by ID, or series + season + episode numbers in one
        call), a whole season, a whole series, or a movie.

        Examples: "Stop monitoring S03E02 of Lioness", "Stop monitoring season 1 of The Capture",
        "Unmonitor the movie Cats"
        """
        if series is not None and episodes:
            if season is None:
                raise ArrError(t("need_season_and_episodes"))
            sonarr = svc.require_sonarr()
            s = await resolve_series(sonarr, series)
            by_number = {e.get("episodeNumber"): e for e in await sonarr.get_episodes(s["id"], season)}
            missing = sorted(set(episodes) - set(by_number))
            if missing:
                raise ArrError(t("episodes_not_in_season", title=s.get("title"), missing=missing, season=season))
            ids = [by_number[n]["id"] for n in sorted(set(episodes))]
            await sonarr.set_episodes_monitored(ids, monitored)
            codes = [fmt.episode_code(season, n) for n in sorted(set(episodes))]
            return {"ok": True, "series": s.get("title"), "episodes": codes, "monitored": monitored}
        if episode_ids:
            await svc.require_sonarr().set_episodes_monitored(episode_ids, monitored)
            return {"ok": True, "episode_ids": episode_ids, "monitored": monitored}
        if series is not None:
            sonarr = svc.require_sonarr()
            s = await resolve_series(sonarr, series)
            if season is None:
                s["monitored"] = monitored
                target = "series"
            else:
                seasons = s.get("seasons") or []
                if not any(se.get("seasonNumber") == season for se in seasons):
                    raise ArrError(t("no_such_season", title=s.get("title"), season=season))
                for se in seasons:
                    if se.get("seasonNumber") == season:
                        se["monitored"] = monitored
                target = f"season {season}"
            updated = await sonarr.update_series(s)
            return {
                "ok": True,
                "series": updated.get("title", s.get("title")),
                "target": target,
                "monitored": monitored,
                "note": t("series_monitor_note") if season is None else None,
            }
        if movie is not None:
            radarr = svc.require_radarr()
            m = await resolve_movie(radarr, movie)
            await radarr.set_movies_monitored([m["id"]], monitored)
            return {"ok": True, "movie": m.get("title"), "monitored": monitored}
        raise ArrError(t("need_monitor_target"))

    @mcp.tool(annotations=DESTRUCTIVE)
    async def remove_from_queue(
        service: ServiceReq,
        queue_ids: Annotated[list[int], Field(min_length=1, description="Queue item IDs (from get_queue)")],
        remove_from_client: Annotated[bool, Field(description="Also delete the task/files in the download client")] = True,
        blocklist: Annotated[bool, Field(description="Add the release to the blocklist")] = False,
        skip_redownload: Annotated[
            bool, Field(description="With blocklist=true, do NOT search for a replacement automatically")
        ] = False,
        confirm: Annotated[bool, Field(description="Required when removing many items at once")] = False,
    ) -> dict[str, Any]:
        """Remove items from the download queue, optionally deleting them from the download
        client and blocklisting the release. With blocklist=true and skip_redownload=false,
        Sonarr/Radarr automatically search for another release. Removing a torrent from the
        client stops seeding (private trackers may count it as hit-and-run). Many items at
        once need confirm=true.

        Examples: "Remove the .exe releases from the queue, blocklist them and find another version",
        "Delete queue item 42 from Download Station"
        """
        client = svc.arrs(service)[0][1]
        ids = list(dict.fromkeys(queue_ids))
        threshold = svc.settings.arr_search_confirm_above
        if len(ids) > threshold and not confirm:
            return {"removed": False, "would_remove": len(ids), "message": t("remove_confirm", n=len(ids))}
        queue = await client.queue()
        by_id = {q["id"]: q for q in queue.get("records") or [] if "id" in q}
        if blocklist and not skip_redownload:
            # Each blocklisted item triggers a new search.
            svc.budget.consume(sum(1 for i in ids if i in by_id))

        async def one(qid: int) -> dict[str, Any]:
            q = by_id.get(qid)
            if q is None:
                return {"id": qid, "removed": False, "error": t("not_in_queue")}
            try:
                await client.remove_from_queue(qid, remove_from_client, blocklist, skip_redownload)
            except ArrError as exc:
                return {"id": qid, "title": q.get("title"), "removed": False, "error": str(exc)}
            return {"id": qid, "title": q.get("title"), "removed": True}

        results = list(await asyncio.gather(*(one(i) for i in ids)))
        out: dict[str, Any] = {
            "service": service,
            "removed_from_client": remove_from_client,
            "blocklisted": blocklist,
            "searching_replacement": blocklist and not skip_redownload,
            "results": results,
        }
        unreleased = [
            q.get("title")
            for i in ids
            if (q := by_id.get(i)) and not_released_yet({**(q.get("episode") or {}), **(q.get("movie") or {})})
        ]
        if blocklist and not skip_redownload and unreleased:
            out["note"] = t("replacement_not_released")
        return out

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def refresh_item(
        series: Annotated[str | int | None, Field(description="Series ID or title")] = None,
        movie: Annotated[str | int | None, Field(description="Movie ID or title")] = None,
    ) -> dict[str, Any]:
        """Refresh metadata and rescan files on disk for a series or movie.

        Examples: "Refresh The Capture", "Rescan the files of Dune"
        """
        if series is not None:
            sonarr = svc.require_sonarr()
            s = await resolve_series(sonarr, series)
            cmd = await sonarr.command("RefreshSeries", seriesIds=[s["id"]])
            return _started(cmd, service="sonarr", series=s.get("title"))
        if movie is not None:
            radarr = svc.require_radarr()
            m = await resolve_movie(radarr, movie)
            cmd = await radarr.command("RefreshMovie", movieIds=[m["id"]])
            return _started(cmd, service="radarr", movie=m.get("title"))
        raise ArrError(t("need_series_or_movie"))

    @mcp.tool(annotations=DESTRUCTIVE)
    @returns_candidates
    async def manual_import(
        service: ServiceReq,
        files: Annotated[
            list[str], Field(min_length=1, description="Exact file paths as seen by Sonarr/Radarr (from find_orphan_downloads)")
        ],
        import_mode: Annotated[
            Literal["auto", "copy", "move"],
            Field(
                description="auto (default, like the web UI): copy/hardlink if the download client is still "
                "seeding, move otherwise. copy: always copy/hardlink. move: always move (breaks seeding)."
            ),
        ] = "auto",
        allow_replace: Annotated[
            bool, Field(description="Allow replacing files that are already in the library (they are deleted)")
        ] = False,
        allow_downgrade: Annotated[
            bool,
            Field(
                description="Also import files Sonarr/Radarr reject as 'not an upgrade' (lower quality or score "
                "than the current file). Only when the user explicitly wants the lower version; needs allow_replace."
            ),
        ] = False,
        matches: Annotated[
            list[ImportMatch] | None,
            Field(description="Manual identification for files that were not matched (or were matched wrongly)"),
        ] = None,
        wait: Annotated[
            bool, Field(description="Wait (up to 2 min) for the import and check that every file really got in")
        ] = True,
    ) -> dict[str, Any]:
        """Import specific files from the downloads folder into the library (all or nothing).
        Never imports a whole folder blindly: every file must be listed, must be matched to a
        series/episode or movie, must have no rejections, and no two files may target the same
        episode or movie. If anything fails, nothing is imported and the problems are returned.
        When Sonarr/Radarr cannot identify a file ("Unknown Series", "matched by ID, manual import
        required"), pass `matches` to assign it by hand; the assignment is re-validated first.
        Replacing a file that is already in the library needs allow_replace=true.
        By default it waits for the import and verifies each file (Sonarr/Radarr report the
        command as successful even when a file fails to move), returning the reason from
        their log for any file that did not get in.

        Examples: "Import /downloads/The.Capture.S03E04.1080p.mkv",
        "Import that file as episode 4 of season 3 of The Capture"
        """
        client = svc.arrs(service)[0][1]
        file_paths = list(dict.fromkeys(files))
        by_path = {m.path: m for m in matches or []}
        unknown = [p for p in by_path if p not in file_paths]
        if unknown:
            raise ArrError(t("match_for_unknown_file", path=unknown[0]))
        timeout = max(svc.settings.arr_timeout, 60.0)
        scans, queue = await asyncio.gather(
            asyncio.gather(*(client.manual_import_scan(p, filter_existing=False, timeout=timeout) for p in file_paths)),
            client.queue(),
        )
        # A file scanned on its own carries no downloadId. Link it to its queue item, so
        # Sonarr/Radarr know the download client still has it ("auto" then copies instead of
        # moving a torrent that is still seeding) and close the queue item afterwards.
        outputs = [(q["outputPath"], q["downloadId"]) for q in queue.get("records") or [] if q.get("outputPath") and q.get("downloadId")]

        problems: list[dict[str, Any]] = []
        planned: list[dict[str, Any]] = []
        command_files: list[dict[str, Any]] = []
        targets: dict[int, list[str]] = {}

        for path, scan in zip(file_paths, scans, strict=True):
            item = next((i for i in scan if i.get("path") == path), None)
            if item is None and len(scan) == 1:
                item = scan[0]
            if item is None:
                problems.append({"path": path, "problem": t("import_not_found")})
                continue
            if path in by_path:
                item, problem = await _apply_match(svc, service, item, by_path[path])
                if problem:
                    problems.append({"path": path, "problem": problem})
                    continue
            if not item.get("downloadId"):
                item["downloadId"] = next((d for out, d in outputs if paths.is_within(path, out)), None)
            rej = fmt.rejections(item)
            downgrade = bool(rej) and all(NOT_UPGRADE_RE.search(r) for r in rej or [])
            if rej and not (downgrade and allow_downgrade):
                problem = t("import_downgrade_needs_allow") if downgrade else t("import_rejected")
                problems.append({"path": path, "problem": problem, "rejections": rej})
                continue
            if downgrade:
                item["_downgrade"] = True
            if service == "sonarr":
                series = item.get("series") or {}
                episodes = item.get("episodes") or []
                if not series.get("id") or not episodes:
                    problems.append({"path": path, "problem": t("import_unidentified_series")})
                    continue
                ep_ids = [e["id"] for e in episodes]
                for eid in ep_ids:
                    targets.setdefault(eid, []).append(path)
                planned.append(
                    {
                        "path": path,
                        "series": series.get("title"),
                        "episodes": [fmt.episode_code(e.get("seasonNumber"), e.get("episodeNumber")) for e in episodes],
                        "replaces_existing_file": any(e.get("hasFile") for e in episodes),
                        "quality": fmt.quality_name(item.get("quality")),
                        "downgrade": item.get("_downgrade") or None,
                        "manual_match": path in by_path or None,
                    }
                )
                command_files.append(
                    {
                        "path": path,
                        "seriesId": series["id"],
                        "episodeIds": ep_ids,
                        "quality": item.get("quality"),
                        "languages": item.get("languages") or [],
                        "releaseGroup": item.get("releaseGroup"),
                        "downloadId": item.get("downloadId"),
                        "indexerFlags": item.get("indexerFlags") or 0,
                        "releaseType": item.get("releaseType") or "unknown",
                    }
                )
            else:
                movie = item.get("movie") or {}
                if not movie.get("id"):
                    problems.append({"path": path, "problem": t("import_unidentified_movie")})
                    continue
                targets.setdefault(movie["id"], []).append(path)
                planned.append(
                    {
                        "path": path,
                        "movie": f"{movie.get('title')} ({movie.get('year')})",
                        "replaces_existing_file": bool(movie.get("hasFile")),
                        "quality": fmt.quality_name(item.get("quality")),
                        "downgrade": item.get("_downgrade") or None,
                        "manual_match": path in by_path or None,
                    }
                )
                command_files.append(
                    {
                        "path": path,
                        "movieId": movie["id"],
                        "quality": item.get("quality"),
                        "languages": item.get("languages") or [],
                        "releaseGroup": item.get("releaseGroup"),
                        "downloadId": item.get("downloadId"),
                        "indexerFlags": item.get("indexerFlags") or 0,
                    }
                )

        target_label = t("target_episode") if service == "sonarr" else t("target_movie")
        for target_id, target_paths in targets.items():
            if len(target_paths) > 1:
                problems.append(
                    {"problem": t("import_same_target", target=target_label, id=target_id), "files": target_paths}
                )

        replacing = [p["path"] for p in planned if p.get("replaces_existing_file")]
        if replacing and not allow_replace:
            problems.append({"problem": t("replace_needs_allow"), "files": replacing})
        planned = [fmt.drop_none(p) for p in planned]
        if problems:
            return {"imported": False, "message": t("nothing_imported"), "problems": problems, "ok_files": planned}

        warning = None
        if replacing:
            try:
                recycle_bin = (await client.media_management()).get("recycleBin")
            except ArrError:
                recycle_bin = "?"
            if not recycle_bin:
                warning = t("recycle_bin_off")
        cmd = await client.command("ManualImport", importMode=import_mode, files=command_files)
        if not wait:
            return _started(cmd, service=service, import_mode=import_mode, files=planned, warning=warning)
        out = {
            "service": service,
            "import_mode": import_mode,
            **await verify_import(client, service, cmd, import_targets(command_files)),
        }
        if warning:
            out["warning"] = warning
        return out


class ImportMatch(BaseModel):
    """Manual assignment of one file for manual_import."""

    path: str = Field(description="File path, exactly as in `files`")
    series: str | int | None = Field(default=None, description="Sonarr: series ID or title")
    season: int | None = Field(default=None, description="Sonarr: season number")
    episodes: list[int] | None = Field(default=None, description="Sonarr: episode numbers within `season`")
    movie: str | int | None = Field(default=None, description="Radarr: movie ID or title")


async def _apply_match(
    svc: Services, service: str, item: dict[str, Any], match: ImportMatch
) -> tuple[dict[str, Any], str | None]:
    """Assign a scanned file by hand and let Sonarr/Radarr re-validate it.

    Returns the re-processed item (with fresh rejections) or a problem message.
    """
    base = {
        "path": item.get("path"),
        "quality": item.get("quality"),
        "languages": item.get("languages") or [],
        "releaseGroup": item.get("releaseGroup"),
        "downloadId": item.get("downloadId"),
        "indexerFlags": item.get("indexerFlags") or 0,
    }
    if service == "sonarr":
        if match.series is None or match.season is None or not match.episodes:
            return item, t("need_season_and_episodes")
        sonarr = svc.require_sonarr()
        series = await resolve_series(sonarr, match.series)
        season_eps = {e.get("episodeNumber"): e for e in await sonarr.get_episodes(series["id"], match.season)}
        missing = [n for n in match.episodes if n not in season_eps]
        if missing:
            codes = ", ".join(fmt.episode_code(match.season, n) or str(n) for n in missing)
            return item, t("match_bad_episodes", title=series.get("title"), codes=codes)
        body = {
            **base,
            "seriesId": series["id"],
            "seasonNumber": match.season,
            "episodeIds": [season_eps[n]["id"] for n in match.episodes],
            "releaseType": item.get("releaseType") or "unknown",
        }
        processed = (await sonarr.manual_import_reprocess([body]))[0]
        # Sonarr returns the episodes but not the series object.
        return {**item, **processed, "series": series}, None

    if match.movie is None:
        return item, t("import_unidentified_movie")
    radarr = svc.require_radarr()
    movie = await resolve_movie(radarr, match.movie)
    processed = (await radarr.manual_import_reprocess([{**base, "movieId": movie["id"]}]))[0]
    return {**item, **processed, "movie": processed.get("movie") or movie}, None


# ----------------------------------------------------------------- helpers


def _lookup_candidate(item: dict[str, Any], id_field: str, id_label: str) -> dict[str, Any]:
    return fmt.drop_none(
        {
            "title": item.get("title"),
            "year": item.get("year"),
            id_label: item.get(id_field),
            "network": item.get("network"),
            "status": item.get("status"),
            "seasons": len(item.get("seasons") or []) or None,
            "overview": fmt.shorten(item.get("overview"), 150),
            "in_library": bool(item.get("id")) or None,
        }
    )


def _pick_lookup(
    results: list[dict[str, Any]], term: str, wanted_id: int | None, id_field: str, id_label: str
) -> dict[str, Any]:
    if not results:
        raise ArrError(t("lookup_empty", term=term))
    if wanted_id is not None:
        for r in results:
            if r.get(id_field) == wanted_id:
                return {"item": r}
        raise ArrError(t("lookup_id_missing", term=term, label=id_label, id=wanted_id))
    if len(results) == 1:
        return {"item": results[0]}
    q = normalize_title(term)
    exact = [r for r in results if normalize_title(r.get("title")) == q]
    if len(exact) == 1:
        return {"item": exact[0]}
    pool = exact or results
    return {
        "added": False,
        "ambiguous": True,
        "message": t("lookup_ambiguous", term=term, label=id_label),
        "candidates": [_lookup_candidate(r, id_field, id_label) for r in pool[:10]],
    }


async def _profile_and_folder(
    client: Any, quality_profile: str | int | None, root_folder: str | None
) -> dict[str, Any]:
    profiles, folders = await asyncio.gather(client.quality_profiles(), client.root_folders())
    profile_id: int | None = None
    if quality_profile is not None:
        for p in profiles:
            if p.get("id") == quality_profile or str(p.get("id")) == str(quality_profile) or normalize_title(
                p.get("name")
            ) == normalize_title(str(quality_profile)):
                profile_id = p["id"]
                break
    folder_path: str | None = None
    if root_folder is not None:
        for f in folders:
            if paths.same(f.get("path") or "", root_folder):
                folder_path = f["path"]
                break

    missing = []
    if profile_id is None:
        missing.append("quality_profile" if quality_profile is None else t("profile_missing", value=quality_profile))
    if folder_path is None:
        missing.append("root_folder" if root_folder is None else t("folder_missing", value=root_folder))
    if missing:
        return {
            "missing": missing,
            "message": t("choose_profile_folder"),
            "quality_profiles": [{"id": p.get("id"), "name": p.get("name")} for p in profiles],
            "root_folders": [
                fmt.drop_none({"path": f.get("path"), "free": fmt.human_size(f.get("freeSpace"))}) for f in folders
            ],
        }
    return {"quality_profile_id": profile_id, "root_folder": folder_path}
