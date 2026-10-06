"""Catalogue tools: series, movies, episodes, wanted lists and calendar."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from arr_doctor import formatting as fmt
from arr_doctor.tools.common import (
    READ_ONLY,
    ServiceOpt,
    Services,
    normalize_title,
    per_service,
    resolve_movie,
    resolve_series,
    returns_candidates,
)

Limit = Annotated[int, Field(ge=1, le=500, description="Max items to return")]
SeriesRef = Annotated[str | int, Field(description="Series ID or title (e.g. 'The Capture')")]
MovieRef = Annotated[str | int, Field(description="Movie ID or title, optionally with year ('Dune 2021')")]


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def search_library(
        query: Annotated[str, Field(description="Text to look for in titles; empty lists everything")] = "",
        service: ServiceOpt = None,
        limit: Limit = fmt.DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Search the local Sonarr/Radarr library (what is already added) by title.

        Does not search the internet; use add_series/add_movie for that.
        Examples: "Do I have The Capture?", "Which Star Wars movies are in my library?"
        """
        q = normalize_title(query)

        async def one(name: str, _client: Any) -> list[dict[str, Any]]:
            summarize: Callable[[dict[str, Any]], dict[str, Any]]
            if name == "sonarr":
                items = await svc.require_sonarr().list_series()
                summarize = fmt.series_summary
            else:
                items = await svc.require_radarr().list_movies()
                summarize = fmt.movie_summary
            hits = []
            for it in items:
                titles = [it.get("title"), it.get("originalTitle")] + [
                    a.get("title") for a in it.get("alternateTitles") or [] if isinstance(a, dict)
                ]
                if not q or any(q in normalize_title(t) for t in titles if t):
                    hits.append({"type": "series" if name == "sonarr" else "movie", **summarize(it)})
            return sorted(hits, key=lambda h: normalize_title(h.get("title")))

        results = await per_service(svc, service, one)
        merged = [h for r in results.values() if isinstance(r, list) for h in r]
        errors = {n: r["error"] for n, r in results.items() if isinstance(r, dict)}
        return fmt.limited(merged, limit, errors=errors or None) if errors else fmt.limited(merged, limit)

    if svc.sonarr:

        @mcp.tool(annotations=READ_ONLY)
        @returns_candidates
        async def get_series(series: SeriesRef) -> dict[str, Any]:
            """Details of one series in Sonarr, including per-season statistics
            (episodes on disk vs aired, monitored seasons, size).

            Examples: "How complete is The Capture?", "Which seasons of Severance are monitored?"
            """
            sonarr = svc.require_sonarr()
            s, profiles = await asyncio.gather(resolve_series(sonarr, series), sonarr.quality_profiles())
            return fmt.series_detail(s, {p["id"]: p["name"] for p in profiles})

        @mcp.tool(annotations=READ_ONLY)
        @returns_candidates
        async def get_episodes(
            series: SeriesRef,
            season: Annotated[int | None, Field(description="Season number; omit for all seasons")] = None,
            only_missing: Annotated[bool, Field(description="Only aired episodes without a file")] = False,
            limit: Limit = 100,
        ) -> dict[str, Any]:
            """Episodes of a series with has_file, monitored, air date and file quality.

            Examples: "Is S03E04 of The Capture downloaded?", "Which episodes of season 2 are missing?"
            """
            sonarr = svc.require_sonarr()
            s = await resolve_series(sonarr, series)
            eps = await sonarr.get_episodes(s["id"], season, include_file=True)
            now = datetime.now(UTC).isoformat()
            if only_missing:
                eps = [e for e in eps if not e.get("hasFile") and (e.get("airDateUtc") or "9999") <= now]
            eps.sort(key=lambda e: (e.get("seasonNumber", 0), e.get("episodeNumber", 0)))
            return fmt.limited(
                [fmt.episode_summary(e) for e in eps],
                limit,
                series={"id": s["id"], "title": s.get("title")},
            )

    if svc.radarr:

        @mcp.tool(annotations=READ_ONLY)
        @returns_candidates
        async def get_movie(movie: MovieRef) -> dict[str, Any]:
            """Details of one movie in Radarr: file, quality, availability, release dates.

            Examples: "Do I have Dune in 4K?", "Why hasn't Oppenheimer downloaded? Is it available yet?"
            """
            radarr = svc.require_radarr()
            m, profiles = await asyncio.gather(resolve_movie(radarr, movie), radarr.quality_profiles())
            return fmt.movie_detail(m, {p["id"]: p["name"] for p in profiles})

    @mcp.tool(annotations=READ_ONLY)
    async def get_missing(
        service: ServiceOpt = None,
        limit: Limit = fmt.DEFAULT_LIMIT,
        monitored_only: bool = True,
    ) -> dict[str, Any]:
        """Wanted/missing: monitored episodes (Sonarr) or movies (Radarr) without a file.

        Examples: "What episodes am I missing?", "Which movies are still not downloaded?"
        """

        async def one(name: str, client: Any) -> dict[str, Any]:
            page = await client.missing(limit, monitored=monitored_only)
            records = page.get("records") or []
            if name == "sonarr":
                items = [fmt.episode_summary(e, with_series=True) for e in records]
            else:
                items = [fmt.movie_summary(m) for m in records]
            return fmt.limited(items, limit, total=page.get("totalRecords"))

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_cutoff_unmet(
        service: ServiceOpt = None,
        limit: Limit = fmt.DEFAULT_LIMIT,
        monitored_only: bool = True,
    ) -> dict[str, Any]:
        """Items that have a file but below the quality profile cutoff (upgrade candidates).

        Examples: "What could be upgraded to better quality?", "Which movies are below cutoff?"
        """

        async def one(name: str, client: Any) -> dict[str, Any]:
            page = await client.cutoff_unmet(limit, monitored=monitored_only)
            records = page.get("records") or []
            if name == "sonarr":
                items = [fmt.episode_summary(e, with_series=True) for e in records]
            else:
                items = [fmt.movie_detail(m) for m in records]
                items = [
                    fmt.drop_none({k: it.get(k) for k in ("id", "title", "year", "file", "quality_profile")})
                    for it in items
                ]
            return fmt.limited(items, limit, total=page.get("totalRecords"))

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    async def get_calendar(
        days_ahead: Annotated[int, Field(ge=0, le=90)] = 7,
        days_back: Annotated[int, Field(ge=0, le=90)] = 0,
        service: ServiceOpt = None,
        include_unmonitored: bool = False,
        limit: Limit = 100,
    ) -> dict[str, Any]:
        """Upcoming (or recent) episode air dates and movie releases.

        Examples: "What airs this week?", "What came out in the last 3 days?"
        """
        now = datetime.now(UTC)
        start = (now - timedelta(days=days_back)).date().isoformat()
        end = (now + timedelta(days=days_ahead)).date().isoformat()

        async def one(name: str, client: Any) -> dict[str, Any]:
            entries = await client.calendar(start, end, unmonitored=include_unmonitored)
            if name == "sonarr":
                items = [fmt.episode_summary(e, with_series=True) for e in entries]
                items.sort(key=lambda e: e.get("air_date") or "")
            else:
                items = []
                for m in entries:
                    s = fmt.movie_summary(m)
                    s.update(
                        fmt.drop_none(
                            {
                                "in_cinemas": m.get("inCinemas"),
                                "digital_release": m.get("digitalRelease"),
                                "physical_release": m.get("physicalRelease"),
                            }
                        )
                    )
                    items.append(s)
            return fmt.limited(items, limit)

        return {"start": start, "end": end, **await per_service(svc, service, one)}
