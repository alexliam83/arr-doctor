"""Maintenance tools: bulk edit, rename with preview, library report, download client test."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from arr_doctor import formatting as fmt
from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t
from arr_doctor.tools.common import (
    READ_ONLY,
    WRITE,
    ArrService,
    ServiceOpt,
    ServiceReq,
    Services,
    ask_user,
    normalize_title,
    per_service,
    resolve_in,
    resolve_movie,
    resolve_series,
    returns_candidates,
)

# Testing download clients connects to them: read-only, but not a closed world.
OPEN_WORLD_READ = {"readOnlyHint": True, "openWorldHint": True}

PREVIEW_LIMIT = 50


def register(mcp: FastMCP, svc: Services, readonly: bool) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def library_report(service: ServiceOpt = None, limit: Annotated[int, Field(ge=1, le=100)] = 10) -> dict[str, Any]:
        """Disk usage and cleanup report: total size, biggest series/movies, unmonitored items
        that still have files, ended series that are complete, size per quality (movies) and
        free space per root folder. Read-only: it never deletes anything.

        Examples: "What takes the most space?", "What could I delete to free space?"
        """

        async def one(name: str, client: Any) -> dict[str, Any]:
            items, roots = await asyncio.gather(
                client.list_series() if name == "sonarr" else client.list_movies(), client.root_folders()
            )
            return _report(name, items, roots, limit)

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    @returns_candidates
    async def preview_rename(
        series: Annotated[str | int | None, Field(description="Sonarr series ID or title")] = None,
        season: Annotated[int | None, Field(description="Only this season")] = None,
        movie: Annotated[str | int | None, Field(description="Radarr movie ID or title")] = None,
        limit: Annotated[int, Field(ge=1, le=500)] = PREVIEW_LIMIT,
    ) -> dict[str, Any]:
        """Preview which files would be renamed by the current naming settings
        (current path -> new path). Nothing is changed. Show it to the user; if they agree,
        apply with rename_files and the confirmation_token returned here.

        Examples: "Which files of The Capture don't follow my naming scheme?",
        "Preview renaming Dune"
        """
        target, files = await _rename_plan(svc, series, season, movie)
        items = [
            fmt.drop_none({"file_id": f["file_id"], "from": f["existing"], "to": f["new"]}) for f in files
        ]
        token = confirmation(target, sorted(f["file_id"] for f in files)) if files else None
        return fmt.drop_none(
            {
                **target,
                **fmt.limited(items, limit),
                "confirmation_token": token,
                "note": await _rename_disabled_note(svc, target),
            }
        )

    @mcp.tool(annotations=OPEN_WORLD_READ)
    async def test_download_clients(service: ServiceOpt = None) -> dict[str, Any]:
        """Test the connection to every download client configured in Sonarr/Radarr
        and report which ones fail and why.

        Examples: "Can Sonarr reach my download client?", "Test the download clients"
        """

        async def one(name: str, client: Any) -> dict[str, Any]:
            clients, results = await asyncio.gather(client.download_clients(), client.test_download_clients())
            names = {c["id"]: c.get("name") for c in clients if "id" in c}
            rows = [
                fmt.drop_none(
                    {
                        "id": r.get("id"),
                        "name": names.get(r.get("id")),
                        "ok": r.get("isValid"),
                        "errors": [f.get("errorMessage") for f in r.get("validationFailures") or [] if f.get("errorMessage")]
                        or None,
                    }
                )
                for r in results or []
            ]
            return {"tested": len(rows), "failing": sum(1 for r in rows if not r.get("ok")), "results": rows}

        return await per_service(svc, service, one)

    @mcp.tool(annotations=READ_ONLY)
    @returns_candidates
    async def bulk_edit_preview(
        service: ServiceReq,
        items: Annotated[list[str | int] | None, Field(description="Series/movie IDs or titles to edit")] = None,
        status: Annotated[
            str | None,
            Field(description="Filter by status. Sonarr: continuing, ended, upcoming. Radarr: announced, inCinemas, released"),
        ] = None,
        monitored: Annotated[bool | None, Field(description="Filter: currently monitored or not")] = None,
        quality_profile: Annotated[str | int | None, Field(description="Filter: current quality profile name or ID")] = None,
        tag: Annotated[str | None, Field(description="Filter: has this tag")] = None,
        year_from: Annotated[int | None, Field(description="Filter: year >= this")] = None,
        year_to: Annotated[int | None, Field(description="Filter: year <= this")] = None,
        complete: Annotated[bool | None, Field(description="Filter: all episodes on disk (series) / has file (movies)")] = None,
        set_monitored: Annotated[bool | None, Field(description="Change: monitor or unmonitor")] = None,
        set_quality_profile: Annotated[str | int | None, Field(description="Change: new quality profile name or ID")] = None,
        add_tags: Annotated[list[str] | None, Field(description="Change: tags to add (created if missing)")] = None,
        remove_tags: Annotated[list[str] | None, Field(description="Change: tags to remove")] = None,
        set_series_type: Annotated[Literal["standard", "daily", "anime"] | None, Field(description="Change (Sonarr)")] = None,
        set_minimum_availability: Annotated[
            Literal["announced", "inCinemas", "released"] | None, Field(description="Change (Radarr)")
        ] = None,
    ) -> dict[str, Any]:
        """Preview a change to many series or movies at once (monitoring, quality profile, tags,
        series type, minimum availability): which items match and what would change. Changes
        nothing. Select items by IDs/titles and/or filters (status, monitored, quality profile,
        tag, year, complete). Show the preview to the user; if they agree, apply it with
        bulk_edit_apply and the confirmation_token returned here.

        Examples: "Which ended series would be unmonitored?", "Preview putting the 4K profile on all 2024 movies"
        """
        return await _bulk_edit(
            svc, None, service, items, status, monitored, quality_profile, tag, year_from, year_to, complete,
            set_monitored, set_quality_profile, add_tags, remove_tags, set_series_type, set_minimum_availability,
            apply=False, confirmation_token=None,
        )

    if readonly:
        return

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def rename_files(
        series: Annotated[str | int | None, Field(description="Sonarr series ID or title")] = None,
        season: Annotated[int | None, Field(description="Only this season")] = None,
        movie: Annotated[str | int | None, Field(description="Radarr movie ID or title")] = None,
        confirmation_token: Annotated[
            str | None, Field(description="Token from preview_rename; required to rename more than one file")
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Rename the files of a series (optionally one season) or a movie to match the
        current naming settings. Call preview_rename first, show it to the user and only call
        this once they agree, passing the preview's confirmation_token (required for more
        than one file).

        Examples: "Yes, rename the files of The Capture season 3", "Apply the rename to Dune"
        """
        target, files = await _rename_plan(svc, series, season, movie)
        if not files:
            note = await _rename_disabled_note(svc, target)
            return {**target, "renamed": 0, "message": note or t("nothing_to_rename")}
        token = confirmation(target, sorted(f["file_id"] for f in files))
        approved_by_user = False
        if len(files) > 1:
            # Ask the user directly when the client can (the model cannot skip this).
            what = target.get("series") or target.get("movie")
            answer = await ask_user(ctx, t("confirm_rename", n=len(files), what=what))
            if answer is False:
                return {**target, "applied": False, "message": t("user_declined")}
            approved_by_user = answer is True
        if len(files) > 1 and not approved_by_user and confirmation_token != token:
            items = [{"file_id": f["file_id"], "from": f["existing"], "to": f["new"]} for f in files]
            return {**target, "applied": False, **fmt.limited(items, PREVIEW_LIMIT), "note": t("needs_preview_token")}
        ids = [f["file_id"] for f in files]
        if target["service"] == "sonarr":
            cmd = await svc.require_sonarr().command("RenameFiles", seriesId=target["series_id"], files=ids)
        else:
            cmd = await svc.require_radarr().command("RenameFiles", movieId=target["movie_id"], files=ids)
        out = fmt.command_summary(cmd)
        out.update(target, files=len(ids), note=t("command_note"))
        return out

    @mcp.tool(annotations=WRITE)
    @returns_candidates
    async def bulk_edit_apply(
        service: ServiceReq,
        items: Annotated[list[str | int] | None, Field(description="Series/movie IDs or titles to edit")] = None,
        status: Annotated[
            str | None,
            Field(description="Filter by status. Sonarr: continuing, ended, upcoming. Radarr: announced, inCinemas, released"),
        ] = None,
        monitored: Annotated[bool | None, Field(description="Filter: currently monitored or not")] = None,
        quality_profile: Annotated[str | int | None, Field(description="Filter: current quality profile name or ID")] = None,
        tag: Annotated[str | None, Field(description="Filter: has this tag")] = None,
        year_from: Annotated[int | None, Field(description="Filter: year >= this")] = None,
        year_to: Annotated[int | None, Field(description="Filter: year <= this")] = None,
        complete: Annotated[bool | None, Field(description="Filter: all episodes on disk (series) / has file (movies)")] = None,
        set_monitored: Annotated[bool | None, Field(description="Change: monitor or unmonitor")] = None,
        set_quality_profile: Annotated[str | int | None, Field(description="Change: new quality profile name or ID")] = None,
        add_tags: Annotated[list[str] | None, Field(description="Change: tags to add (created if missing)")] = None,
        remove_tags: Annotated[list[str] | None, Field(description="Change: tags to remove")] = None,
        set_series_type: Annotated[Literal["standard", "daily", "anime"] | None, Field(description="Change (Sonarr)")] = None,
        set_minimum_availability: Annotated[
            Literal["announced", "inCinemas", "released"] | None, Field(description="Change (Radarr)")
        ] = None,
        confirmation_token: Annotated[
            str | None,
            Field(description="Token from bulk_edit_preview; required for several items or a filter selection"),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Apply a change to many series or movies at once. For several items or a filter
        selection, call bulk_edit_preview first, show it to the user and only call this once
        they agree, passing the preview's confirmation_token (same selection and changes). A
        single item named by the user can be changed directly. Root folders are not changed
        here because that would move files.

        Examples: "Yes, unmonitor those ended series", "Tag The Capture with 'uk'"
        """
        return await _bulk_edit(
            svc, ctx, service, items, status, monitored, quality_profile, tag, year_from, year_to, complete,
            set_monitored, set_quality_profile, add_tags, remove_tags, set_series_type, set_minimum_availability,
            apply=True, confirmation_token=confirmation_token,
        )

# ------------------------------------------------------------------ helpers


async def _bulk_edit(
    svc: Services,
    ctx: Any,
    service: ArrService,
    items: list[str | int] | None,
    status: str | None,
    monitored: bool | None,
    quality_profile: str | int | None,
    tag: str | None,
    year_from: int | None,
    year_to: int | None,
    complete: bool | None,
    set_monitored: bool | None,
    set_quality_profile: str | int | None,
    add_tags: list[str] | None,
    remove_tags: list[str] | None,
    set_series_type: str | None,
    set_minimum_availability: str | None,
    *,
    apply: bool,
    confirmation_token: str | None,
) -> dict[str, Any]:
    client: Any = svc.arrs(service)[0][1]
    filters = {
        "status": status, "monitored": monitored, "quality_profile": quality_profile, "tag": tag,
        "year_from": year_from, "year_to": year_to, "complete": complete,
    }
    if not items and all(v is None for v in filters.values()):
        raise ArrError(t("bulk_need_selection"))
    if service == "sonarr" and set_minimum_availability is not None:
        raise ArrError(t("bulk_wrong_service", field="set_minimum_availability", svc="Radarr"))
    if service == "radarr" and set_series_type is not None:
        raise ArrError(t("bulk_wrong_service", field="set_series_type", svc="Sonarr"))
    changes_given = [set_monitored, set_quality_profile, add_tags, remove_tags, set_series_type, set_minimum_availability]
    if all(c is None or c == [] for c in changes_given):
        raise ArrError(t("bulk_need_change"))

    all_items, profiles, tags = await asyncio.gather(
        client.list_series() if service == "sonarr" else client.list_movies(),
        client.quality_profiles(),
        client.tags(),
    )
    profile_names = {p["id"]: p.get("name") for p in profiles}
    tag_by_id = {tg["id"]: tg.get("label") for tg in tags}
    tag_by_label = {normalize_title(tg.get("label")): tg["id"] for tg in tags}

    selected = all_items
    if items:
        wanted: set[int] = set()
        kind: Literal["series", "movies"] = "series" if service == "sonarr" else "movies"
        for ref in items:
            wanted.add((await resolve_in(all_items, ref, kind))["id"])
        selected = [it for it in selected if it.get("id") in wanted]
    selected = _apply_filters(service, selected, filters, profiles, tag_by_label)

    new_profile_id = _profile_id(profiles, set_quality_profile) if set_quality_profile is not None else None
    if set_quality_profile is not None and new_profile_id is None:
        raise ArrError(t("profile_missing", value=set_quality_profile))
    changes = fmt.drop_none(
        {
            "monitored": set_monitored,
            "quality_profile": profile_names.get(new_profile_id) if new_profile_id else None,
            "add_tags": add_tags or None,
            "remove_tags": remove_tags or None,
            "series_type": set_series_type,
            "minimum_availability": set_minimum_availability,
        }
    )
    def describe(items: list[dict[str, Any]], tag_names: dict[int, Any]) -> list[dict[str, Any]]:
        return [
            fmt.drop_none(
                {
                    "id": it.get("id"),
                    "title": it.get("title"),
                    "year": it.get("year"),
                    "monitored": it.get("monitored"),
                    "quality_profile": profile_names.get(it.get("qualityProfileId") or -1),
                    "tags": [tag_names.get(x, x) for x in it.get("tags") or []] or None,
                }
            )
            for it in items
        ]

    preview = describe(selected, tag_by_id)
    result: dict[str, Any] = {"service": service, "matched": len(selected), "changes": changes}
    # A single item named by the user is exactly what they asked for. Several items, or
    # a filter selection, must have been previewed (and shown) first: the token proves it.
    token = confirmation(service, sorted(it["id"] for it in selected), changes)
    needs_token = len(selected) > 1 or any(v is not None for v in filters.values())
    if apply and selected and needs_token:
        # Ask the user directly when the client can (the model cannot skip this).
        names = ", ".join(str(it.get("title")) for it in selected[:10]) + (" …" if len(selected) > 10 else "")
        answer = await ask_user(
            ctx, t("confirm_bulk_edit", n=len(selected), changes=json.dumps(changes, ensure_ascii=False), items=names)
        )
        if answer is False:
            return {**result, "applied": False, "message": t("user_declined")}
        if answer is True:
            needs_token = False
    if not apply or not selected or (needs_token and confirmation_token != token):
        if not selected:
            note = t("bulk_nothing_matched")
        elif apply:
            note = t("needs_preview_token")
        else:
            note = t("bulk_preview_note")
        result.update(
            applied=False,
            items=fmt.limited(preview, PREVIEW_LIMIT),
            confirmation_token=token if selected else None,
            note=note,
        )
        return fmt.drop_none(result)

    ids_key = "seriesIds" if service == "sonarr" else "movieIds"
    ids = [it["id"] for it in selected]
    body: dict[str, Any] = {ids_key: ids}
    if set_monitored is not None:
        body["monitored"] = set_monitored
    if new_profile_id is not None:
        body["qualityProfileId"] = new_profile_id
    if set_series_type is not None:
        body["seriesType"] = set_series_type
    if set_minimum_availability is not None:
        body["minimumAvailability"] = set_minimum_availability
    if add_tags:
        add_ids = []
        for label in add_tags:
            tag_id = tag_by_label.get(normalize_title(label))
            if tag_id is None:
                tag_id = (await client.create_tag(label))["id"]
            add_ids.append(tag_id)
        body.update(tags=add_ids, applyTags="add")

    edit = client.edit_series if service == "sonarr" else client.edit_movies
    if len(body) > 1:
        await edit(body)
    if remove_tags:
        remove_ids = [tag_by_label[k] for k in (normalize_title(x) for x in remove_tags) if k in tag_by_label]
        if remove_ids:
            await edit({ids_key: ids, "tags": remove_ids, "applyTags": "remove"})
    # Read the items back: show what Sonarr/Radarr actually stored, not what we asked for.
    after_items, after_tags = await asyncio.gather(
        client.list_series() if service == "sonarr" else client.list_movies(), client.tags()
    )
    changed = set(ids)
    after = [it for it in after_items if it.get("id") in changed]
    result.update(applied=True, items=fmt.limited(describe(after, {tg["id"]: tg.get("label") for tg in after_tags}), PREVIEW_LIMIT))
    if service == "sonarr" and set_monitored is not None:
        result["note"] = t("series_monitor_note")
    return result



async def _rename_plan(
    svc: Services, series: str | int | None, season: int | None, movie: str | int | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if series is not None:
        sonarr = svc.require_sonarr()
        s = await resolve_series(sonarr, series)
        rows = await sonarr.rename_preview(s["id"], season)
        target = fmt.drop_none({"service": "sonarr", "series": s.get("title"), "series_id": s["id"], "season": season})
        files = [
            {
                "file_id": r.get("episodeFileId"),
                "existing": r.get("existingPath"),
                "new": r.get("newPath"),
            }
            for r in rows
            if r.get("episodeFileId")
        ]
        return target, files
    if movie is not None:
        radarr = svc.require_radarr()
        m = await resolve_movie(radarr, movie)
        rows = await radarr.rename_preview(m["id"])
        target = {"service": "radarr", "movie": f"{m.get('title')} ({m.get('year')})", "movie_id": m["id"]}
        files = [
            {"file_id": r.get("movieFileId"), "existing": r.get("existingPath"), "new": r.get("newPath")}
            for r in rows
            if r.get("movieFileId")
        ]
        return target, files
    raise ArrError(t("need_series_or_movie"))


async def _rename_disabled_note(svc: Services, target: dict[str, Any]) -> str | None:
    """Explain an empty rename list when renaming is switched off in Media Management."""
    service = target["service"]
    client: Any = svc.require_sonarr() if service == "sonarr" else svc.require_radarr()
    try:
        naming = await client.naming_config()
    except ArrError:
        return None
    key = "renameEpisodes" if service == "sonarr" else "renameMovies"
    if naming.get(key) is False:
        return t("rename_disabled", svc=client.display_name, setting=key)
    return None


def confirmation(*parts: Any) -> str:
    """Short token tying an apply call to the exact preview it follows (same items, same changes)."""
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _profile_id(profiles: list[dict[str, Any]], ref: str | int) -> int | None:
    for p in profiles:
        if str(p.get("id")) == str(ref) or normalize_title(p.get("name")) == normalize_title(str(ref)):
            return p["id"]
    return None


def _apply_filters(
    service: str,
    items: list[dict[str, Any]],
    f: dict[str, Any],
    profiles: list[dict[str, Any]],
    tag_by_label: dict[str, int],
) -> list[dict[str, Any]]:
    out = items
    if f["status"] is not None:
        out = [it for it in out if (it.get("status") or "").casefold() == f["status"].casefold()]
    if f["monitored"] is not None:
        out = [it for it in out if bool(it.get("monitored")) == f["monitored"]]
    if f["quality_profile"] is not None:
        pid = _profile_id(profiles, f["quality_profile"])
        if pid is None:
            raise ArrError(t("profile_missing", value=f["quality_profile"]))
        out = [it for it in out if it.get("qualityProfileId") == pid]
    if f["tag"] is not None:
        tid = tag_by_label.get(normalize_title(f["tag"]))
        out = [it for it in out if tid is not None and tid in (it.get("tags") or [])]
    if f["year_from"] is not None:
        out = [it for it in out if (it.get("year") or 0) >= f["year_from"]]
    if f["year_to"] is not None:
        out = [it for it in out if (it.get("year") or 0) <= f["year_to"]]
    if f["complete"] is not None:
        out = [it for it in out if _is_complete(service, it) == f["complete"]]
    return out


def _is_complete(service: str, it: dict[str, Any]) -> bool:
    if service == "radarr":
        return bool(it.get("hasFile"))
    st = it.get("statistics") or {}
    return (st.get("episodeCount") or 0) > 0 and (st.get("episodeFileCount") or 0) >= (st.get("episodeCount") or 0)


def _size(service: str, it: dict[str, Any]) -> int:
    if service == "sonarr":
        return (it.get("statistics") or {}).get("sizeOnDisk") or 0
    return it.get("sizeOnDisk") or (it.get("statistics") or {}).get("sizeOnDisk") or 0


def _report(service: str, items: list[dict[str, Any]], roots: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    def row(it: dict[str, Any]) -> dict[str, Any]:
        return fmt.drop_none(
            {"id": it.get("id"), "title": it.get("title"), "year": it.get("year"), "size": fmt.human_size(_size(service, it))}
        )

    with_files = [it for it in items if _size(service, it) > 0]
    biggest = sorted(with_files, key=lambda it: _size(service, it), reverse=True)
    unmonitored = [it for it in biggest if not it.get("monitored")]
    out: dict[str, Any] = {
        "items": len(items),
        "items_with_files": len(with_files),
        "total_size": fmt.human_size(sum(_size(service, it) for it in items)),
        "biggest": [row(it) for it in biggest[:limit]],
        "unmonitored_with_files": {
            "count": len(unmonitored),
            "size": fmt.human_size(sum(_size(service, it) for it in unmonitored)),
            "top": [row(it) for it in unmonitored[:limit]],
        },
        "root_folders": [
            fmt.drop_none({"path": r.get("path"), "free": fmt.human_size(r.get("freeSpace")), "accessible": r.get("accessible")})
            for r in roots
        ],
    }
    if service == "sonarr":
        ended = [it for it in biggest if it.get("ended") or it.get("status") == "ended"]
        complete = [it for it in ended if _is_complete(service, it)]
        out["ended_and_complete"] = {
            "count": len(complete),
            "size": fmt.human_size(sum(_size(service, it) for it in complete)),
            "top": [row(it) for it in complete[:limit]],
        }
        missing = sum(
            max(0, ((it.get("statistics") or {}).get("episodeCount") or 0) - ((it.get("statistics") or {}).get("episodeFileCount") or 0))
            for it in items
            if it.get("monitored")
        )
        out["missing_episodes_monitored"] = missing
    else:
        by_quality: Counter[str] = Counter()
        size_by_quality: Counter[str] = Counter()
        for it in with_files:
            q = fmt.quality_name((it.get("movieFile") or {}).get("quality")) or "?"
            by_quality[q] += 1
            size_by_quality[q] += _size(service, it)
        out["by_quality"] = [
            {"quality": q, "movies": n, "size": fmt.human_size(size_by_quality[q])} for q, n in by_quality.most_common()
        ]
        out["missing_monitored"] = sum(1 for it in items if it.get("monitored") and not it.get("hasFile"))
    return out
