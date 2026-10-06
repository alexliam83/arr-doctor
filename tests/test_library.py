from __future__ import annotations

import httpx

from tests.conftest import R, S, load


def _library(api) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))


async def test_search_library_both(api, call) -> None:
    _library(api)
    out = await call.ok("search_library", query="capture")
    assert out["total"] == 1
    item = out["items"][0]
    assert item["type"] == "series" and item["title"] == "The Capture"
    assert "overview" not in item and "images" not in item


async def test_search_library_limit_and_truncated(api, call) -> None:
    _library(api)
    out = await call.ok("search_library", limit=2)
    assert out["returned"] == 2 and out["truncated"] is True and out["total"] == 8


async def test_search_library_error(api, call) -> None:
    api.get(f"{S}/series").respond(401)
    msg = await call.error("search_library", query="x", service="sonarr")
    assert "401" in msg and "API key" in msg


async def test_get_series_by_title_with_seasons(api, call) -> None:
    _library(api)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    out = await call.ok("get_series", series="the capture")
    assert out["id"] == 1
    assert out["quality_profile"] == "HD-1080p"
    s3 = next(s for s in out["season_stats"] if s["season"] == 3)
    assert s3 == {"season": 3, "monitored": True, "on_disk": 3, "aired": 4, "total": 6, "size": "6.98 GB"}
    assert len(out["overview"]) <= 200


async def test_get_series_ambiguous_returns_candidates(api, call) -> None:
    _library(api)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    out = await call.ok("get_series", series="The Office")
    assert out["ambiguous"] is True
    assert {c["year"] for c in out["candidates"]} == {2001, 2005}


async def test_get_series_title_with_year(api, call) -> None:
    _library(api)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    out = await call.ok("get_series", series="The Office (2005)")
    assert out["id"] == 2


async def test_get_series_numeric_title_wins(api, call) -> None:
    _library(api)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    out = await call.ok("get_series", series="24")
    assert out["title"] == "24"


async def test_get_series_by_id(api, call) -> None:
    api.get(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    out = await call.ok("get_series", series=1)
    assert out["title"] == "The Capture"


async def test_get_series_not_found_suggests(api, call) -> None:
    _library(api)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    msg = await call.error("get_series", series="The Captre")
    assert "No encontré ninguna serie" in msg and "The Capture" in msg


async def test_get_episodes_season(api, call) -> None:
    _library(api)
    route = api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    out = await call.ok("get_episodes", series="The Capture", season=3)
    assert route.calls.last.request.url.params["seasonNumber"] == "3"
    e4 = next(e for e in out["items"] if e["code"] == "S03E04")
    assert e4["has_file"] is False and e4["monitored"] is True
    e1 = out["items"][0]
    assert e1["file"]["quality"] == "WEBDL-1080p"


async def test_get_episodes_only_missing_excludes_future(api, call) -> None:
    _library(api)
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    out = await call.ok("get_episodes", series="The Capture", season=3, only_missing=True)
    assert [e["code"] for e in out["items"]] == ["S03E04"]


async def test_get_episodes_timeout(api, call) -> None:
    api.get(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    api.get(f"{S}/episode").mock(side_effect=httpx.ReadTimeout("slow"))
    msg = await call.error("get_episodes", series=1)
    assert "no respondió" in msg


async def test_get_movie_with_year(api, call) -> None:
    _library(api)
    api.get(f"{R}/qualityprofile").respond(json=load("radarr_qualityprofile"))
    out = await call.ok("get_movie", movie="Dune 2021")
    assert out["id"] == 1 and out["file"]["quality"] == "Bluray-1080p"


async def test_get_movie_ambiguous(api, call) -> None:
    _library(api)
    api.get(f"{R}/qualityprofile").respond(json=load("radarr_qualityprofile"))
    out = await call.ok("get_movie", movie="Dune")
    assert out["ambiguous"] and len(out["candidates"]) == 2


async def test_get_movie_error(api, call) -> None:
    api.get(f"{R}/movie/9").respond(404)
    api.get(f"{R}/qualityprofile").respond(json=load("radarr_qualityprofile"))
    assert "404" in await call.error("get_movie", movie=9)


async def test_get_missing(api, call) -> None:
    api.get(f"{S}/wanted/missing").respond(json=load("sonarr_wanted_missing"))
    api.get(f"{R}/wanted/missing").respond(json=load("radarr_wanted_missing"))
    out = await call.ok("get_missing")
    assert out["sonarr"]["items"][0]["series"] == "The Capture"
    assert out["sonarr"]["items"][0]["code"] == "S03E04"
    assert out["radarr"]["total"] == 2


async def test_get_missing_error(api, call) -> None:
    api.get(f"{R}/wanted/missing").respond(401)
    assert "Radarr devolvió 401" in await call.error("get_missing", service="radarr")


async def test_get_cutoff_unmet(api, call) -> None:
    api.get(f"{S}/wanted/cutoff").respond(json=load("sonarr_wanted_cutoff"))
    out = await call.ok("get_cutoff_unmet", service="sonarr")
    assert out["sonarr"]["items"][0]["file"]["quality"] == "WEBDL-1080p"


async def test_get_cutoff_unmet_error(api, call) -> None:
    api.get(f"{S}/wanted/cutoff").mock(side_effect=httpx.ConnectError("x"))
    assert "No se pudo conectar" in await call.error("get_cutoff_unmet", service="sonarr")


async def test_get_calendar(api, call) -> None:
    route = api.get(f"{S}/calendar").respond(json=load("sonarr_calendar"))
    api.get(f"{R}/calendar").respond(json=[load("radarr_movie_3")])
    out = await call.ok("get_calendar", days_ahead=3)
    assert "start" in route.calls.last.request.url.params
    assert out["sonarr"]["items"][0]["code"] == "S03E05"
    assert out["radarr"]["items"][0]["digital_release"].startswith("2023")


async def test_get_calendar_error(api, call) -> None:
    api.get(f"{S}/calendar").respond(500, json={"message": "boom"})
    assert "500" in await call.error("get_calendar", service="sonarr")
