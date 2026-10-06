"""Turn raw *arr API payloads into compact dicts that are cheap for the model.

Rules: no images, no internal fields, overviews capped at 200 characters, every
list goes through :func:`limited` / :func:`paged` so it carries ``truncated``.
"""

from __future__ import annotations

from typing import Any

OVERVIEW_MAX = 200
DEFAULT_LIMIT = 50


def shorten(text: str | None, n: int = OVERVIEW_MAX) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def human_size(num: float | int | None) -> str | None:
    if num is None:
        return None
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.2f} {unit}"
        size /= 1024
    return None  # pragma: no cover


def drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def limited(items: list[Any], limit: int, total: int | None = None, **extra: Any) -> dict[str, Any]:
    """Wrap a list with count + ``truncated`` flag."""
    total = len(items) if total is None else total
    out = items[:limit]
    return {"total": total, "returned": len(out), "truncated": total > len(out), **extra, "items": out}


def episode_code(season: int | None, episode: int | None) -> str | None:
    if season is None or episode is None:
        return None
    return f"S{season:02d}E{episode:02d}"


def quality_name(q: dict[str, Any] | None) -> str | None:
    if not q:
        return None
    return (q.get("quality") or {}).get("name")


def language_names(langs: list[dict[str, Any]] | None) -> list[str] | None:
    if not langs:
        return None
    return [str(lang["name"]) for lang in langs if lang.get("name")]


# ---------------------------------------------------------------- Sonarr


def series_summary(s: dict[str, Any]) -> dict[str, Any]:
    stats = s.get("statistics") or {}
    return drop_none(
        {
            "id": s.get("id"),
            "title": s.get("title"),
            "year": s.get("year"),
            "status": s.get("status"),
            "monitored": s.get("monitored"),
            "network": s.get("network"),
            "seasons": stats.get("seasonCount"),
            "episodes_on_disk": stats.get("episodeFileCount"),
            "episodes_aired": stats.get("episodeCount"),
            "percent": round(stats["percentOfEpisodes"], 1) if stats.get("percentOfEpisodes") is not None else None,
            "size": human_size(stats.get("sizeOnDisk")),
            "tvdb_id": s.get("tvdbId"),
        }
    )


def series_detail(s: dict[str, Any], quality_profiles: dict[int, str] | None = None) -> dict[str, Any]:
    out = series_summary(s)
    out.update(
        drop_none(
            {
                "overview": shorten(s.get("overview")),
                "path": s.get("path"),
                "quality_profile": (quality_profiles or {}).get(s.get("qualityProfileId") or -1)
                or s.get("qualityProfileId"),
                "series_type": s.get("seriesType"),
                "next_airing": s.get("nextAiring"),
                "previous_airing": s.get("previousAiring"),
                "imdb_id": s.get("imdbId"),
            }
        )
    )
    seasons = []
    for season in s.get("seasons") or []:
        st = season.get("statistics") or {}
        seasons.append(
            drop_none(
                {
                    "season": season.get("seasonNumber"),
                    "monitored": season.get("monitored"),
                    "on_disk": st.get("episodeFileCount"),
                    "aired": st.get("episodeCount"),
                    "total": st.get("totalEpisodeCount"),
                    "size": human_size(st.get("sizeOnDisk")),
                    "next_airing": st.get("nextAiring"),
                }
            )
        )
    if seasons:
        out["season_stats"] = seasons
    return out


def episode_summary(e: dict[str, Any], with_series: bool = False) -> dict[str, Any]:
    out = {
        "id": e.get("id"),
        "code": episode_code(e.get("seasonNumber"), e.get("episodeNumber")),
        "title": e.get("title"),
        "air_date": e.get("airDateUtc") or e.get("airDate"),
        "has_file": e.get("hasFile"),
        "monitored": e.get("monitored"),
    }
    if e.get("finaleType"):
        out["finale"] = e["finaleType"]
    ef = e.get("episodeFile")
    if ef:
        out["file"] = drop_none(
            {
                "quality": quality_name(ef.get("quality")),
                "size": human_size(ef.get("size")),
                "relative_path": ef.get("relativePath"),
            }
        )
    if e.get("lastSearchTime"):
        out["last_search"] = e["lastSearchTime"]
    if with_series:
        series = e.get("series") or {}
        out = {"series": series.get("title"), "series_id": e.get("seriesId"), **out}
    return drop_none(out)


# ---------------------------------------------------------------- Radarr


def movie_summary(m: dict[str, Any]) -> dict[str, Any]:
    return drop_none(
        {
            "id": m.get("id"),
            "title": m.get("title"),
            "year": m.get("year"),
            "status": m.get("status"),
            "monitored": m.get("monitored"),
            "has_file": m.get("hasFile"),
            "is_available": m.get("isAvailable"),
            "size": human_size(m.get("sizeOnDisk")) if m.get("sizeOnDisk") else None,
            "tmdb_id": m.get("tmdbId"),
        }
    )


def movie_detail(m: dict[str, Any], quality_profiles: dict[int, str] | None = None) -> dict[str, Any]:
    out = movie_summary(m)
    mf = m.get("movieFile") or {}
    out.update(
        drop_none(
            {
                "original_title": m.get("originalTitle") if m.get("originalTitle") != m.get("title") else None,
                "overview": shorten(m.get("overview")),
                "studio": m.get("studio"),
                "runtime_min": m.get("runtime") or None,
                "path": m.get("path"),
                "quality_profile": (quality_profiles or {}).get(m.get("qualityProfileId") or -1)
                or m.get("qualityProfileId"),
                "minimum_availability": m.get("minimumAvailability"),
                "in_cinemas": m.get("inCinemas"),
                "digital_release": m.get("digitalRelease"),
                "physical_release": m.get("physicalRelease"),
                "imdb_id": m.get("imdbId"),
                "last_search": m.get("lastSearchTime"),
                "file": drop_none(
                    {
                        "relative_path": mf.get("relativePath"),
                        "quality": quality_name(mf.get("quality")),
                        "size": human_size(mf.get("size")),
                        "release_group": mf.get("releaseGroup"),
                    }
                )
                if mf
                else None,
            }
        )
    )
    return out


# ------------------------------------------------------------ diagnostics


def status_messages(q: dict[str, Any]) -> list[str] | None:
    msgs: list[str] = []
    for sm in q.get("statusMessages") or []:
        title = sm.get("title")
        inner = [m for m in (sm.get("messages") or []) if m]
        if inner:
            msgs.extend(f"{title}: {m}" if title and title != m else m for m in inner)
        elif title:
            msgs.append(title)
    return msgs or None


def queue_item(q: dict[str, Any], service: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": q.get("id"),
        "service": service,
        "title": q.get("title"),
        "status": q.get("status"),
        "state": q.get("trackedDownloadState"),
        "health": q.get("trackedDownloadStatus"),
        "messages": status_messages(q),
        "error": q.get("errorMessage"),
        "quality": quality_name(q.get("quality")),
        "size": human_size(q.get("size")),
        "left": human_size(q.get("sizeleft")) if q.get("sizeleft") else None,
        "time_left": q.get("timeleft"),
        "indexer": q.get("indexer") or None,
        "download_client": q.get("downloadClient"),
        "protocol": q.get("protocol"),
        "output_path": q.get("outputPath"),
        "download_id": q.get("downloadId"),
        "added": q.get("added"),
    }
    if service == "sonarr":
        series = q.get("series") or {}
        ep = q.get("episode") or {}
        out["series"] = series.get("title")
        out["series_id"] = q.get("seriesId")
        out["episode"] = episode_code(ep.get("seasonNumber"), ep.get("episodeNumber"))
        out["episode_id"] = q.get("episodeId")
        out["episode_has_file"] = q.get("episodeHasFile")
    else:
        movie = q.get("movie") or {}
        out["movie"] = movie.get("title")
        out["movie_id"] = q.get("movieId")
    return drop_none(out)


def group_queue(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group queue records by download.

    Sonarr lists a season pack as one queue record per episode, all with the same
    downloadId; showing them separately repeats the same download N times.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for q in records:
        key = q.get("downloadId") or f"queue-{q.get('id')}"
        groups.setdefault(key, []).append(q)
    return list(groups.values())


def queue_items(records: list[dict[str, Any]], service: str) -> list[dict[str, Any]]:
    """One formatted entry per download (see :func:`group_queue`)."""
    out = []
    for group in group_queue(records):
        item = queue_item(group[0], service)
        if len(group) > 1:
            eps = [q.get("episode") or {} for q in group]
            codes = sorted(c for c in (episode_code(e.get("seasonNumber"), e.get("episodeNumber")) for e in eps) if c)
            item.pop("episode", None)
            item.pop("episode_id", None)
            item["episodes"] = codes or None
            item["episode_ids"] = [q.get("episodeId") for q in group if q.get("episodeId")]
            item["queue_ids"] = [q.get("id") for q in group]
        out.append(drop_none(item))
    return out


_HISTORY_DATA_KEYS = (
    "indexer",
    "releaseGroup",
    "downloadClient",
    "downloadClientName",
    "message",
    "reason",
    "droppedPath",
    "importedPath",
    "size",
)


def history_item(h: dict[str, Any], service: str) -> dict[str, Any]:
    data = h.get("data") or {}
    extra = {k: data[k] for k in _HISTORY_DATA_KEYS if data.get(k)}
    if "size" in extra and str(extra["size"]).isdigit():
        extra["size"] = human_size(int(extra["size"]))
    if "message" in extra:
        extra["message"] = shorten(extra["message"], 300)
    out: dict[str, Any] = {
        "id": h.get("id"),
        "date": h.get("date"),
        "event": h.get("eventType"),
        "source_title": h.get("sourceTitle"),
        "quality": quality_name(h.get("quality")),
        "download_id": h.get("downloadId"),
        **extra,
    }
    if service == "sonarr":
        ep = h.get("episode") or {}
        out["series"] = (h.get("series") or {}).get("title")
        out["series_id"] = h.get("seriesId")
        out["episode"] = episode_code(ep.get("seasonNumber"), ep.get("episodeNumber"))
        out["episode_id"] = h.get("episodeId")
    else:
        out["movie"] = (h.get("movie") or {}).get("title")
        out["movie_id"] = h.get("movieId")
    return drop_none(out)


def blocklist_item(b: dict[str, Any], service: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": b.get("id"),
        "date": b.get("date"),
        "source_title": b.get("sourceTitle"),
        "indexer": b.get("indexer") or None,
        "reason": shorten(b.get("message"), 300),
        "quality": quality_name(b.get("quality")),
        "protocol": b.get("protocol"),
    }
    if service == "sonarr":
        out["series"] = (b.get("series") or {}).get("title")
        out["series_id"] = b.get("seriesId")
        out["episode_ids"] = b.get("episodeIds")
    else:
        out["movie"] = (b.get("movie") or {}).get("title")
        out["movie_id"] = b.get("movieId")
    return drop_none(out)


def command_summary(c: dict[str, Any]) -> dict[str, Any]:
    return drop_none(
        {
            "command_id": c.get("id"),
            "name": c.get("name") or c.get("commandName"),
            "status": c.get("status"),
            "result": c.get("result"),
            "message": c.get("message"),
            "queued": c.get("queued"),
            "started": c.get("started"),
            "ended": c.get("ended"),
            "exception": shorten(c.get("exception"), 300),
        }
    )


def rejections(item: dict[str, Any]) -> list[str] | None:
    out = []
    for r in item.get("rejections") or []:
        reason = r.get("reason") if isinstance(r, dict) else str(r)
        kind = r.get("type") if isinstance(r, dict) else None
        if reason:
            out.append(f"{reason} ({kind})" if kind else reason)
    return out or None
