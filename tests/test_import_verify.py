"""manual_import must not trust the command status: verify each file got in.

Reproduces a real case: Sonarr reported "Manually imported 6 files" / successful,
but every move failed because a *file* named "Season 3" blocked the season folder.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from arr_doctor.tools import importcheck
from tests.conftest import R, S, load

E04 = "/downloads/The.Capture.S03E04.1080p.WEB.H264-NTb/the.capture.s03e04.1080p.mkv"
QUEUED = "2026-10-04T18:17:25Z"


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importcheck, "IMPORT_POLL_SECONDS", 0.0)


def _command(status: str) -> dict:
    return {**load("sonarr_command_queued"), "id": 77, "status": status, "queued": QUEUED,
            "result": "successful" if status == "completed" else "unknown"}


def _mock_command(api, base: str, statuses: list[str]):
    api.post(f"{base}/command").respond(json=_command("queued"))
    responses = [httpx.Response(200, json=_command(s)) for s in statuses]
    return api.get(f"{base}/command/77").mock(side_effect=responses)


async def test_import_verified(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_s03e04"))
    _mock_command(api, S, ["started", "completed"])
    ep = {**load("sonarr_episodes_s3")[3], "hasFile": True,
          "episodeFile": {"id": 900, "dateAdded": "2026-10-04T18:17:40Z", "relativePath": "Season 03/x.mkv"}}
    route = api.get(f"{S}/episode").respond(json=[ep])
    out = await call.ok("manual_import", service="sonarr", files=[E04])
    assert out["result"] == "imported" and out["imported"] == [E04]
    assert "failed" not in out
    assert route.calls.last.request.url.params["includeEpisodeFile"] == "true"


async def test_import_reported_successful_but_failed(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_s03e04"))
    _mock_command(api, S, ["completed"])
    api.get(f"{S}/episode").respond(json=[load("sonarr_episodes_s3")[3]])  # still no file
    name = E04.split("/")[-1]
    api.get(f"{S}/log").respond(json={"records": [
        {"time": "2026-10-04T18:17:30Z", "level": "warn", "logger": "ImportApprovedEpisodes",
         "message": f"Couldn't import episode {E04}: Not a directory"},
        {"time": "2026-10-04T10:00:00Z", "level": "warn", "message": f"old message about {name}"},
    ]})
    out = await call.ok("manual_import", service="sonarr", files=[E04])
    assert out["result"] == "failed" and out["imported"] == []
    assert out["failed"] == [{"path": E04, "reason": "Not a directory"}]
    assert "No se ha perdido nada" in out["note"]
    assert out["command"]["result"] == "successful"  # what Sonarr claimed


async def test_old_file_is_not_mistaken_for_a_new_import(api, call) -> None:
    """With allow_replace, the episode already had a file: only a newer one counts."""
    api.get(f"{S}/queue").respond(json={"records": []})
    item = load("sonarr_manualimport_s03e04")
    item[0]["episodes"][0]["hasFile"] = True
    api.get(f"{S}/manualimport").respond(json=item)
    api.get(f"{S}/config/mediamanagement").respond(json={"recycleBin": "/recycle"})
    _mock_command(api, S, ["completed"])
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    ep = {**load("sonarr_episodes_s3")[3], "hasFile": True, "episodeFile": {"id": 5, "dateAdded": old}}
    api.get(f"{S}/episode").respond(json=[ep])
    api.get(f"{S}/log").respond(json={"records": []})
    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_replace=True)
    assert out["result"] == "failed" and out["failed"] == [{"path": E04}]


async def test_import_still_running(api, call, monkeypatch: pytest.MonkeyPatch) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    monkeypatch.setattr(importcheck, "IMPORT_WAIT_SECONDS", 0.0)
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_s03e04"))
    api.post(f"{S}/command").respond(json=_command("queued"))
    out = await call.ok("manual_import", service="sonarr", files=[E04])
    assert out["result"] == "still_running" and "get_command_status" in out["note"]


async def test_radarr_import_verified(api, call) -> None:
    api.get(f"{R}/queue").respond(json={"records": []})
    path = "/downloads/Past.Lives.2023.1080p.BluRay.x264-FLUX/Past.Lives.2023.1080p.mkv"
    api.get(f"{R}/manualimport").respond(json=load("radarr_manualimport_pastlives"))
    _mock_command(api, R, ["completed"])
    movie = {**load("radarr_movie_3"), "hasFile": True, "movieFile": {"id": 1, "dateAdded": "2026-10-04T18:18:00Z"}}
    api.get(f"{R}/movie/3").respond(json=movie)
    out = await call.ok("manual_import", service="radarr", files=[path])
    assert out["result"] == "imported"


def test_diagnose_path_conflict() -> None:
    from arr_doctor.tools.troubleshoot import diagnose

    assert diagnose(["Couldn't import episode /downloads/x.mkv: Not a directory"])[0] == "path_conflict"
    assert diagnose(["Unable to create directory: /series/X/Season 3: The file '/series/X/Season 3' already exists."]) == ["path_conflict"]


async def test_get_command_status_verifies_finished_import(api, call) -> None:
    body = {"files": [{"path": E04, "seriesId": 1, "episodeIds": [304]}], "importMode": "auto"}
    api.get(f"{S}/command/77").respond(json={**_command("completed"), "name": "ManualImport", "body": body})
    api.get(f"{S}/episode").respond(json=[load("sonarr_episodes_s3")[3]])
    api.get(f"{S}/log").respond(json={"records": [
        {"time": "2026-10-04T18:17:30Z", "message": f"Couldn't import episode {E04}: Not a directory"}]})
    out = await call.ok("get_command_status", service="sonarr", command_id=77)
    assert out["result"] == "failed" and out["failed"][0]["reason"] == "Not a directory"


async def test_get_command_status_import_still_running(api, call) -> None:
    body = {"files": [{"path": E04, "seriesId": 1, "episodeIds": [304]}]}
    api.get(f"{S}/command/77").respond(
        json={**_command("started"), "name": "ManualImport", "message": "Processing file 4 of 6", "body": body}
    )
    out = await call.ok("get_command_status", service="sonarr", command_id=77)
    assert out["status"] == "started" and out["message"] == "Processing file 4 of 6"
    assert "get_command_status" in out["note"]


async def test_later_import_does_not_count_for_an_earlier_failed_command(api, call) -> None:
    """Real case: command A failed at 18:17, command B imported the same files at 18:29."""
    body = {"files": [{"path": E04, "seriesId": 1, "episodeIds": [304]}]}
    api.get(f"{S}/command/77").respond(
        json={**_command("completed"), "name": "ManualImport", "ended": "2026-10-04T18:17:45Z", "body": body}
    )
    ep = {**load("sonarr_episodes_s3")[3], "hasFile": True, "episodeFile": {"id": 9, "dateAdded": "2026-10-04T18:29:00Z"}}
    api.get(f"{S}/episode").respond(json=[ep])
    api.get(f"{S}/log").respond(json={"records": []})
    out = await call.ok("get_command_status", service="sonarr", command_id=77)
    assert out["result"] == "failed"
