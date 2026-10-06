from __future__ import annotations

import json

import httpx

from tests.conftest import P, load


async def test_list_indexers(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    api.get(f"{P}/indexerstatus").respond(json=load("prowlarr_indexerstatus"))
    out = await call.ok("list_indexers")
    by = {i["name"]: i for i in out["items"]}
    assert by["TheRARBG"]["enabled"] is False
    # Disabled by the user: shown as disabled, with a note that it had been failing too.
    assert by["TheRARBG"]["state"] == "disabled" and "disabled_until" not in by["TheRARBG"]
    assert by["TheRARBG"]["last_failure"] == "2026-10-04T12:00:00Z" and by["TheRARBG"]["note"]
    assert by["1337x"]["prowlarr_id"] == 1
    assert by["LimeTorrents"]["priority"] == 30
    assert "fields" not in by["1337x"]


async def test_list_indexers_status_failure_is_tolerated(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    api.get(f"{P}/indexerstatus").respond(500)
    out = await call.ok("list_indexers")
    assert out["total"] == 3


async def test_list_indexers_error(api, call) -> None:
    api.get(f"{P}/indexer").respond(401)
    assert "Prowlarr devolvió 401" in await call.error("list_indexers")


async def test_get_indexer_stats_sorted_by_failures(api, call) -> None:
    route = api.get(f"{P}/indexerstats").respond(json=load("prowlarr_indexerstats"))
    out = await call.ok("get_indexer_stats", start_date="2026-10-01")
    params = route.calls.last.request.url.params
    assert params["startDate"] == "2026-10-01" and "endDate" in params
    assert [i["name"] for i in out["indexers"]] == ["LimeTorrents", "TheRARBG", "1337x"]
    # (120 failed searches + 3 failed RSS + 2 failed grabs) / (400 + 100 + 10)
    assert out["indexers"][0]["failure_rate"] == 24.5 and out["indexers"][0]["failures"] == 125


async def test_rss_only_failures_rank_first(api, call) -> None:
    """Real case: dead indexers fail 30/30 RSS calls and are never searched."""
    stats = load("prowlarr_indexerstats")
    stats["indexers"].append({"indexerId": 9, "indexerName": "EZTV", "numberOfQueries": 0, "numberOfGrabs": 0,
                              "numberOfRssQueries": 30, "numberOfFailedRssQueries": 30, "numberOfFailedQueries": 0,
                              "numberOfFailedGrabs": 0, "numberOfFailedAuthQueries": 0})
    api.get(f"{P}/indexerstats").respond(json=stats)
    out = await call.ok("get_indexer_stats")
    assert out["indexers"][0]["name"] == "EZTV" and out["indexers"][0]["failure_rate"] == 100.0


async def test_list_indexers_state(api, call) -> None:
    from datetime import UTC, datetime, timedelta

    indexers = load("prowlarr_indexers")
    future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    status = [{"id": 1, "indexerId": 2, "disabledTill": future}, {"id": 2, "indexerId": 1, "disabledTill": "2020-01-01T00:00:00Z"}]
    api.get(f"{P}/indexer").respond(json=indexers)
    api.get(f"{P}/indexerstatus").respond(json=status)
    out = await call.ok("list_indexers")
    state = {i["name"]: i["state"] for i in out["items"]}
    assert state == {"1337x": "ok", "LimeTorrents": "failing", "TheRARBG": "disabled"}


async def test_get_indexer_stats_error(api, call) -> None:
    api.get(f"{P}/indexerstats").mock(side_effect=httpx.ConnectError("x"))
    msg = await call.error("get_indexer_stats")
    assert "Prowlarr" in msg and "PROWLARR_URL" in msg


async def test_set_indexer_enabled_by_name(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    api.get(f"{P}/indexer/2").respond(json=load("prowlarr_indexer_2"))
    route = api.put(f"{P}/indexer/2").respond(json={**load("prowlarr_indexer_2"), "enable": False})
    out = await call.ok("set_indexer_enabled", indexer="limetorrents", enabled=False)
    sent = json.loads(route.calls.last.request.content)
    assert sent["enable"] is False and sent["fields"]  # full resource is sent back
    assert out == {"changed": True, "indexer": "LimeTorrents", "enabled": False}


async def test_set_indexer_enabled_noop(api, call) -> None:
    api.get(f"{P}/indexer/2").respond(json=load("prowlarr_indexer_2"))
    put = api.put(f"{P}/indexer/2").respond(json={})
    out = await call.ok("set_indexer_enabled", indexer=2, enabled=True)
    assert out["changed"] is False and not put.called


async def test_set_indexer_enabled_unknown(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    msg = await call.error("set_indexer_enabled", indexer="nyaa", enabled=False)
    assert "Disponibles: 1337x, LimeTorrents, TheRARBG" in msg


async def test_set_indexer_enabled_error(api, call) -> None:
    api.get(f"{P}/indexer/2").respond(401)
    assert "401" in await call.error("set_indexer_enabled", indexer=2, enabled=False)


async def test_test_indexers(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    api.post(f"{P}/indexer/testall").respond(400, json=load("prowlarr_testall"))
    out = await call.ok("test_indexers")
    assert out["tested"] == 2 and out["failing"] == 1
    assert out["results"][0]["name"] == "LimeTorrents" and "Unable to connect" in out["results"][0]["errors"][0]


async def test_test_indexers_error(api, call) -> None:
    api.get(f"{P}/indexer").respond(json=load("prowlarr_indexers"))
    api.post(f"{P}/indexer/testall").mock(side_effect=httpx.ReadTimeout("x"))
    assert "no respondió en 120 s" in await call.error("test_indexers")
