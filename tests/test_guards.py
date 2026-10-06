"""Guardrails that keep the server within Sonarr/Radarr good practice."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastmcp import Client

from arr_doctor.clients.base import ArrError
from arr_doctor.guards import IndexerBudget, recently_searched
from arr_doctor.server import build_server
from tests.conftest import R, S, load, make_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_budget_sliding_window() -> None:
    clock = FakeClock()
    budget = IndexerBudget(3, clock=clock)
    budget.consume(2)
    budget.consume(1)
    with pytest.raises(ArrError, match="3 "):
        budget.consume(1)
    clock.now = 3599
    with pytest.raises(ArrError):
        budget.consume(1)
    clock.now = 3600  # the first three expire
    budget.consume(3)
    assert budget.used == 3


def test_budget_disabled() -> None:
    budget = IndexerBudget(0)
    for _ in range(1000):
        budget.consume(5)


def test_recently_searched() -> None:
    now = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert recently_searched("2026-10-04T11:30:00Z", 60, now)
    assert not recently_searched("2026-10-04T10:30:00Z", 60, now)
    assert not recently_searched(None, 60, now)
    assert not recently_searched("2026-10-04T11:59:00Z", 0, now)  # cooldown off
    assert not recently_searched("garbage", 60, now)


def _episode(eid: int, minutes_ago: int | None) -> dict:
    ep = {**load("sonarr_episodes_s3")[3], "id": eid, "episodeNumber": eid}
    if minutes_ago is not None:
        ep["lastSearchTime"] = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    return ep


async def test_recently_searched_episodes_are_skipped(api, call) -> None:
    api.get(f"{S}/episode").respond(json=[_episode(1, 5), _episode(2, None), _episode(3, 600)])
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", episode_ids=[1, 2, 3])
    assert json.loads(cmd.calls.last.request.content)["episodeIds"] == [2, 3]
    assert len(out["skipped_recently_searched"]) == 1


async def test_all_recently_searched_does_nothing_unless_forced(api, call) -> None:
    api.get(f"{S}/episode").respond(json=[_episode(1, 5)])
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", episode_ids=[1])
    assert out["searched"] is False and not cmd.called
    await call.ok("search_episodes", episode_ids=[1], force=True)
    assert cmd.called


async def test_big_episode_search_needs_confirm(api, call) -> None:
    api.get(f"{S}/episode").respond(json=[_episode(i, None) for i in range(1, 13)])
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", episode_ids=list(range(1, 13)))
    assert out == {"searched": False, "would_search": 12, "message": out["message"]}
    assert "confirm=true" in out["message"] and not cmd.called
    await call.ok("search_episodes", episode_ids=list(range(1, 13)), confirm=True)
    assert cmd.called


async def test_search_missing_needs_confirm_over_threshold(api, call) -> None:
    missing = {**load("radarr_wanted_missing"), "totalRecords": 250}
    api.get(f"{R}/wanted/missing").respond(json=missing)
    cmd = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    out = await call.ok("search_missing", service="radarr")
    assert out["radarr"]["would_search"] == 250 and not cmd.called
    out = await call.ok("search_missing", service="radarr", confirm=True)
    assert cmd.called and out["radarr"]["items"] == 250


async def test_search_missing_nothing_to_do(api, call) -> None:
    api.get(f"{R}/wanted/missing").respond(json={"totalRecords": 0, "records": []})
    cmd = api.post(f"{R}/command").respond(json={})
    out = await call.ok("search_missing", service="radarr")
    assert out["radarr"]["would_search"] == 0 and not cmd.called


async def test_indexer_budget_blocks_search_loops(api) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    release = api.get(f"{S}/release").respond(json=[])
    async with Client(build_server(make_settings(arr_indexer_budget_per_hour=3))) as c:
        for _ in range(3):
            res = await c.call_tool("explain_search", {"series": "The Capture", "season": 3, "episode": 4})
            assert not res.is_error
        res = await c.call_tool(
            "explain_search", {"series": "The Capture", "season": 3, "episode": 4}, raise_on_error=False
        )
    assert res.is_error and "ARR_INDEXER_BUDGET_PER_HOUR" in res.content[0].text
    assert release.call_count == 3  # the fourth search never reached the indexers


async def test_budget_checked_before_removing_with_redownload(api) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    delete = api.delete(url__regex=rf"{S}/queue/\d+").respond(200)
    async with Client(build_server(make_settings(arr_indexer_budget_per_hour=1))) as c:
        res = await c.call_tool(
            "remove_from_queue", {"service": "sonarr", "queue_ids": [11, 12], "blocklist": True}, raise_on_error=False
        )
    assert res.is_error and not delete.called  # nothing removed if the replacement searches don't fit


async def test_mass_queue_removal_needs_confirm(api, call) -> None:
    delete = api.delete(url__regex=rf"{S}/queue/\d+").respond(200)
    out = await call.ok("remove_from_queue", service="sonarr", queue_ids=list(range(1, 20)))
    assert out["would_remove"] == 19 and not delete.called


E04 = "/downloads/The.Capture.S03E04.1080p.WEB.H264-NTb/the.capture.s03e04.1080p.mkv"


async def test_manual_import_replacing_needs_allow_and_warns_without_recycle_bin(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    item = load("sonarr_manualimport_s03e04")
    item[0]["episodes"][0]["hasFile"] = True
    api.get(f"{S}/manualimport").respond(json=item)
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    api.get(f"{S}/config/mediamanagement").respond(json={"recycleBin": "", "copyUsingHardlinks": True})
    out = await call.ok("manual_import", service="sonarr", files=[E04], wait=False)
    assert out["imported"] is False and "allow_replace" in out["problems"][0]["problem"] and not cmd.called
    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_replace=True, wait=False)
    assert cmd.called and "papelera" in out["warning"]


async def test_manual_import_replacing_with_recycle_bin_has_no_warning(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    item = load("sonarr_manualimport_s03e04")
    item[0]["episodes"][0]["hasFile"] = True
    api.get(f"{S}/manualimport").respond(json=item)
    api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    api.get(f"{S}/config/mediamanagement").respond(json={"recycleBin": "/recycle"})
    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_replace=True, wait=False)
    assert "warning" not in out


async def test_guard_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ARR_SEARCH_CONFIRM_ABOVE", "3")
    monkeypatch.setenv("ARR_SEARCH_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("ARR_INDEXER_BUDGET_PER_HOUR", "0")
    from arr_doctor.config import Settings

    s = Settings(_env_file=None)
    assert (s.arr_search_confirm_above, s.arr_search_cooldown_minutes, s.arr_indexer_budget_per_hour) == (3, 0, 0)


async def test_typo_in_title_does_not_spend_indexer_budget(api) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    async with Client(build_server(make_settings(arr_indexer_budget_per_hour=1))) as c:
        bad = await c.call_tool("explain_search", {"series": "Nonexistent Show", "season": 1}, raise_on_error=False)
        assert bad.is_error
        api.get(f"{S}/release").respond(json=[])
        ok = await c.call_tool("explain_search", {"series": "The Capture", "season": 3}, raise_on_error=False)
    assert not ok.is_error  # the failed lookup did not use the only search left


async def test_downgrade_needs_explicit_permission_and_links_the_download(api, call) -> None:
    """Real case: the user wants a 1080p pack instead of the 2160p files Sonarr keeps."""
    item = load("sonarr_manualimport_s03e04")
    item[0]["episodes"][0]["hasFile"] = True
    item[0]["rejections"] = [{"reason": "Not an upgrade for existing episode file(s). Existing quality: WEBDL-2160p. "
                                        "New Quality WEBDL-1080p.", "type": "permanent"}]
    item[0].pop("downloadId", None)
    api.get(f"{S}/manualimport").respond(json=item)
    folder = E04.rsplit("/", 1)[0]
    queue = {"records": [{**load("sonarr_queue")["records"][0], "downloadId": "pack-9", "outputPath": folder}]}
    api.get(f"{S}/queue").respond(json=queue)
    api.get(f"{S}/config/mediamanagement").respond(json={"recycleBin": ""})
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))

    out = await call.ok("manual_import", service="sonarr", files=[E04], wait=False)
    assert out["imported"] is False and "allow_downgrade" in out["problems"][0]["problem"] and not cmd.called

    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_downgrade=True, wait=False)
    assert out["imported"] is False and "allow_replace" in out["problems"][0]["problem"] and not cmd.called

    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_downgrade=True, allow_replace=True, wait=False)
    sent = json.loads(cmd.calls.last.request.content)
    assert sent["files"][0]["downloadId"] == "pack-9"  # linked to the queue item: "auto" won't break seeding
    assert out["files"][0]["downgrade"] is True and "papelera" in out["warning"]


async def test_allow_downgrade_does_not_skip_other_rejections(api, call) -> None:
    item = load("sonarr_manualimport_s03e04")
    item[0]["rejections"] = [{"reason": "Not an upgrade for existing episode file(s)", "type": "permanent"},
                             {"reason": "Sample", "type": "permanent"}]
    api.get(f"{S}/manualimport").respond(json=item)
    api.get(f"{S}/queue").respond(json={"records": []})
    cmd = api.post(f"{S}/command").respond(json={})
    out = await call.ok("manual_import", service="sonarr", files=[E04], allow_downgrade=True, allow_replace=True, wait=False)
    assert out["imported"] is False and not cmd.called


async def test_unaired_episodes_are_not_searched_unless_forced(api, call) -> None:
    """Real case: an episode airing tomorrow only had fake .exe releases."""
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    unaired = {**_episode(10, None), "airDateUtc": future}
    api.get(f"{S}/episode").respond(json=[unaired, _episode(2, None)])
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", episode_ids=[10, 2])
    assert json.loads(cmd.calls.last.request.content)["episodeIds"] == [2]
    assert out["skipped_not_released"] and "skipped_recently_searched" not in out

    api.get(f"{S}/episode").respond(json=[unaired])
    out = await call.ok("search_episodes", episode_ids=[10])
    assert out["searched"] is False and "RSS" in out["message"]
    await call.ok("search_episodes", episode_ids=[10], force=True)
    assert json.loads(cmd.calls.last.request.content)["episodeIds"] == [10]


async def test_unavailable_movie_is_not_searched(api, call) -> None:
    movies = load("radarr_movie_list")
    movies[2]["isAvailable"] = False
    api.get(f"{R}/movie").respond(json=movies)
    cmd = api.post(f"{R}/command").respond(json={})
    out = await call.ok("search_movie", movies=["Past Lives"])
    assert out["searched"] is False and not cmd.called


async def test_remove_with_replacement_warns_when_unreleased(api, call) -> None:
    queue = load("sonarr_queue")
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    queue["records"][0]["episode"]["airDateUtc"] = future  # item 11: not aired yet
    api.get(f"{S}/queue").respond(json=queue)
    api.delete(url__regex=rf"{S}/queue/\d+").respond(200)
    out = await call.ok("remove_from_queue", service="sonarr", queue_ids=[11], blocklist=True)
    assert "skip_redownload=true" in out["note"]
    out = await call.ok("remove_from_queue", service="sonarr", queue_ids=[12], blocklist=True)  # S03E04 aired
    assert "note" not in out
