"""Checking that a ManualImport really put each file in the library.

Sonarr/Radarr mark a ManualImport command "successful" even when every file fails
to move (seen on a real NAS: "Manually imported 6 files" while all six failed with
"Not a directory"). The command status alone is therefore not trustworthy.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from arr_doctor import formatting as fmt
from arr_doctor import paths
from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t

# MCP clients often give up on a tool call after about a minute, and moving files
# between volumes on a NAS can take several minutes: wait a little, then hand over
# to get_command_status, which runs the same verification once the command ends.
IMPORT_POLL_SECONDS = 3.0
IMPORT_WAIT_SECONDS = 40.0

Targets = dict[str, tuple[list[int], int | None]]


def import_targets(files: list[dict[str, Any]]) -> Targets:
    """path -> (episode ids, movie id) from ManualImport command files."""
    return {f["path"]: (list(f.get("episodeIds") or []), f.get("movieId")) for f in files if f.get("path")}


async def verify_import(client: Any, service: str, cmd: dict[str, Any], targets: Targets) -> dict[str, Any]:
    status = cmd
    waited = 0.0
    while status.get("status") in ("queued", "started") and waited < IMPORT_WAIT_SECONDS:
        await asyncio.sleep(IMPORT_POLL_SECONDS)
        waited += IMPORT_POLL_SECONDS
        status = await client.command_status(cmd["id"])
    summary = fmt.command_summary(status)
    if status.get("status") in ("queued", "started"):
        return {"result": "still_running", "command": summary, "note": t("import_still_running")}

    queued_at = parse_iso(status.get("queued")) or datetime.now(UTC)
    ended_at = parse_iso(status.get("ended")) or datetime.now(UTC)
    skew = timedelta(seconds=60)  # clock differences between the NAS and here

    def fresh(file: dict[str, Any] | None) -> bool:
        # The file must have been added *by this command*: not before it (an old file
        # that was not replaced) and not after it (a later import of the same episode).
        added = parse_iso((file or {}).get("dateAdded"))
        return bool(added and queued_at - skew <= added <= ended_at + skew)

    ok: dict[str, bool] = {}
    if service == "sonarr":
        ids = sorted({i for eps, _ in targets.values() for i in eps})
        episodes = {e["id"]: e for e in await client.get_episodes_by_id(ids, include_file=True)} if ids else {}
        for path, (eps, _) in targets.items():
            ok[path] = bool(eps) and all(fresh(episodes.get(i, {}).get("episodeFile")) for i in eps)
    else:
        for path, (_, movie_id) in targets.items():
            movie = await client.get_movie(movie_id) if movie_id else {}
            ok[path] = fresh(movie.get("movieFile"))

    failed_paths = [p for p, good in ok.items() if not good]
    reasons: dict[str, str] = {}
    if failed_paths:
        try:
            logs = (await client.logs(200, level="warn")).get("records") or []
        except ArrError:
            logs = []
        for p in failed_paths:
            name = paths.basename(p)
            for rec in logs:
                when = parse_iso(rec.get("time"))
                msg = rec.get("message") or ""
                if when and when >= queued_at - timedelta(seconds=5) and (p in msg or name in msg):
                    reasons[p] = fmt.shorten(msg.split(": ", 1)[-1] if p in msg else msg, 300) or ""
                    break
    imported = [p for p, good in ok.items() if good]
    failed = [fmt.drop_none({"path": p, "reason": reasons.get(p)}) for p in failed_paths]
    result = "imported" if not failed else ("failed" if not imported else "partial")
    out: dict[str, Any] = {"result": result, "imported": imported, "command": summary}
    if failed:
        out["failed"] = failed
        out["note"] = t("import_verify_failed", svc=client.display_name)
    return out


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
