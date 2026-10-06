from __future__ import annotations

import json

import httpx

from tests.conftest import R, S, load


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ---------------------------------------------------------------- searches


async def test_search_episodes_by_ids(api, call) -> None:
    api.get(f"{S}/episode").respond(json=[load("sonarr_episodes_s3")[3]])
    route = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", episode_ids=[304])
    assert body(route) == {"name": "EpisodeSearch", "episodeIds": [304]}
    assert out["command_id"] == 1234 and out["status"] == "queued"


async def test_search_episodes_by_numbers(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    route = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_episodes", series="The Capture", season=3, episodes=[4])
    assert body(route)["episodeIds"] == [304]
    assert out["episodes"] == ["The Capture S03E04"]


async def test_search_episodes_unknown_episode(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    msg = await call.error("search_episodes", series="The Capture", season=3, episodes=[9])
    assert "[9]" in msg


async def test_search_episodes_error(api, call) -> None:
    api.get(f"{S}/episode").respond(json=[load("sonarr_episodes_s3")[3]])
    api.post(f"{S}/command").respond(401)
    assert "401" in await call.error("search_episodes", episode_ids=[1])


async def test_search_season(api, call) -> None:
    api.get(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    route = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    await call.ok("search_season", series=1, season=3)
    assert body(route) == {"name": "SeasonSearch", "seriesId": 1, "seasonNumber": 3}


async def test_search_season_error(api, call) -> None:
    api.get(f"{S}/series/1").mock(side_effect=httpx.ConnectError("x"))
    assert "No se pudo conectar" in await call.error("search_season", series=1, season=3)


async def test_search_missing_both(api, call) -> None:
    api.get(f"{S}/wanted/missing").respond(json=load("sonarr_wanted_missing"))
    api.get(f"{R}/wanted/missing").respond(json=load("radarr_wanted_missing"))
    s = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    r = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    out = await call.ok("search_missing")
    assert body(s) == {"name": "MissingEpisodeSearch", "monitored": True}
    assert out["sonarr"]["items"] == 1 and out["radarr"]["items"] == 2
    assert body(r) == {"name": "MissingMoviesSearch"}
    assert set(out) == {"sonarr", "radarr"}


async def test_search_missing_one_series(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    s = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("search_missing", series="The Capture")
    assert body(s)["seriesId"] == 1 and "radarr" not in out


async def test_search_missing_error(api, call) -> None:
    api.get(f"{R}/wanted/missing").respond(json=load("radarr_wanted_missing"))
    api.post(f"{R}/command").respond(500, json={"message": "x"})
    assert "500" in await call.error("search_missing", service="radarr")


async def test_search_movie(api, call) -> None:
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_list")[0])
    route = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    out = await call.ok("search_movie", movies=["Past Lives", 1])
    assert body(route) == {"name": "MoviesSearch", "movieIds": [3, 1]}
    assert out["movies"] == ["Past Lives (2023)", "Dune (2021)"]


async def test_search_movie_ambiguous(api, call) -> None:
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    out = await call.ok("search_movie", movies=["Dune"])
    assert out["ambiguous"] is True


async def test_search_movie_error(api, call) -> None:
    api.get(f"{R}/movie/3").respond(401)
    assert "401" in await call.error("search_movie", movies=[3])


# -------------------------------------------------------------- monitoring


async def test_set_monitored_episodes(api, call) -> None:
    route = api.put(f"{S}/episode/monitor").respond(json=[])
    await call.ok("set_monitored", monitored=False, episode_ids=[301, 302])
    assert body(route) == {"episodeIds": [301, 302], "monitored": False}


async def test_set_monitored_season(api, call) -> None:
    api.get(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    route = api.put(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    out = await call.ok("set_monitored", monitored=False, series=1, season=1)
    sent = body(route)
    assert next(s for s in sent["seasons"] if s["seasonNumber"] == 1)["monitored"] is False
    assert next(s for s in sent["seasons"] if s["seasonNumber"] == 2)["monitored"] is True
    assert sent["monitored"] is True
    assert out["target"] == "season 1"


async def test_set_monitored_bad_season(api, call) -> None:
    api.get(f"{S}/series/1").respond(json=load("sonarr_series_1"))
    assert "no tiene temporada 9" in await call.error("set_monitored", monitored=True, series=1, season=9)


async def test_set_monitored_movie(api, call) -> None:
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    route = api.put(f"{R}/movie/editor").respond(json={})
    await call.ok("set_monitored", monitored=False, movie="Past Lives")
    assert body(route) == {"movieIds": [3], "monitored": False}


async def test_set_monitored_error(api, call) -> None:
    api.put(f"{S}/episode/monitor").respond(401)
    assert "401" in await call.error("set_monitored", monitored=True, episode_ids=[1])


# ------------------------------------------------------------ queue removal


async def test_remove_exe_from_queue_with_blocklist(api, call) -> None:
    """Phase 2 'done when': find the .exe releases, remove + blocklist + search again."""
    for base, kind in ((S, "sonarr"), (R, "radarr")):
        api.get(f"{base}/queue").respond(json=load(f"{kind}_queue"))
        api.get(f"{base}/history/since").respond(json=load(f"{kind}_history_since"))
        api.get(f"{base}/blocklist").respond(json=load(f"{kind}_blocklist"))
    suspicious = await call.ok("find_suspicious_releases")
    ids = [q["id"] for q in suspicious["sonarr"]["queue"]]
    assert ids == [12]

    delete = api.delete(f"{S}/queue/12").respond(200)
    out = await call.ok("remove_from_queue", service="sonarr", queue_ids=ids, blocklist=True)
    params = delete.calls.last.request.url.params
    assert params["removeFromClient"] == "true"
    assert params["blocklist"] == "true"
    assert params["skipRedownload"] == "false"
    assert out["searching_replacement"] is True
    assert out["results"] == [{"id": 12, "title": "The.Capture.S03E04.1080p.WEB.H264-FAKE", "removed": True}]


async def test_remove_from_queue_unknown_id_and_partial_failure(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.delete(f"{S}/queue/11").respond(500, json={"message": "client error"})
    out = await call.ok("remove_from_queue", service="sonarr", queue_ids=[11, 99])
    by = {r["id"]: r for r in out["results"]}
    assert by[99]["error"] == "no está en la cola"
    assert by[11]["removed"] is False and "500" in by[11]["error"]


async def test_remove_from_queue_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    assert "401" in await call.error("remove_from_queue", service="sonarr", queue_ids=[1])


# ----------------------------------------------------------------- refresh


async def test_refresh_series(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    route = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    await call.ok("refresh_item", series="capture")
    assert body(route) == {"name": "RefreshSeries", "seriesIds": [1]}


async def test_refresh_movie(api, call) -> None:
    api.get(f"{R}/movie/4").respond(json=load("radarr_movie_list")[3])
    route = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    await call.ok("refresh_item", movie=4)
    assert body(route) == {"name": "RefreshMovie", "movieIds": [4]}


async def test_refresh_error(api, call) -> None:
    assert "Indica `series` o `movie`" in await call.error("refresh_item")


# --------------------------------------------------------------------- add


def _profiles(api, base, kind) -> None:
    api.get(f"{base}/qualityprofile").respond(json=load(f"{kind}_qualityprofile"))
    api.get(f"{base}/rootfolder").respond(json=load(f"{kind}_rootfolder"))


async def test_add_series_ambiguous_lookup(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(json=load("sonarr_series_lookup") + load("sonarr_series_lookup_single"))
    out = await call.ok("add_series", term="Sev")
    assert out["ambiguous"] is True and len(out["candidates"]) == 3


async def test_add_series_returns_options_when_missing(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(json=load("sonarr_series_lookup_single"))
    _profiles(api, S, "sonarr")
    out = await call.ok("add_series", term="Slow Horses")
    assert out["added"] is False
    assert out["missing"] == ["quality_profile", "root_folder"]
    assert {p["name"] for p in out["quality_profiles"]} == {"HD-1080p", "HD - 720p/1080p"}
    assert out["root_folders"][0]["path"] == "/tv"


async def test_add_series_ok(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(json=load("sonarr_series_lookup"))
    _profiles(api, S, "sonarr")
    added = {**load("sonarr_series_lookup")[0], "id": 50, "path": "/tv/Severance"}
    route = api.post(f"{S}/series").respond(201, json=added)
    out = await call.ok(
        "add_series", term="Severance", tvdb_id=371980, quality_profile="hd-1080p", root_folder="/tv/"
    )
    sent = body(route)
    assert sent["tvdbId"] == 371980 and sent["qualityProfileId"] == 4 and sent["rootFolderPath"] == "/tv"
    assert sent["addOptions"] == {
        "monitor": "all",
        "searchForMissingEpisodes": True,
        "searchForCutoffUnmetEpisodes": False,
    }
    assert out["added"] is True and out["series"]["id"] == 50


async def test_add_series_exact_title_disambiguates(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(json=load("sonarr_series_lookup"))
    _profiles(api, S, "sonarr")
    out = await call.ok("add_series", term="Severance", quality_profile=4)
    assert out["series"]["tvdb_id"] == 371980 and out["missing"] == ["root_folder"]


async def test_add_series_already_in_library(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(json=[load("sonarr_series_1")])
    out = await call.ok("add_series", term="The Capture")
    assert out["added"] is False and "ya está" in out["message"]


async def test_add_series_error(api, call) -> None:
    api.get(f"{S}/series/lookup").respond(401)
    assert "401" in await call.error("add_series", term="x")


async def test_add_movie_ok(api, call) -> None:
    api.get(f"{R}/movie/lookup").respond(json=load("radarr_movie_lookup"))
    _profiles(api, R, "radarr")
    route = api.post(f"{R}/movie").respond(201, json={**load("radarr_movie_lookup")[0], "id": 77})
    out = await call.ok("add_movie", term="Past Lives", quality_profile="Ultra-HD", root_folder="/movies")
    sent = body(route)
    assert sent["qualityProfileId"] == 5 and sent["minimumAvailability"] == "released"
    assert sent["addOptions"] == {"searchForMovie": True, "monitor": "movieOnly"}
    assert out["added"] is True


async def test_add_movie_unknown_profile(api, call) -> None:
    api.get(f"{R}/movie/lookup").respond(json=load("radarr_movie_lookup"))
    _profiles(api, R, "radarr")
    out = await call.ok("add_movie", term="Past Lives", quality_profile="4K", root_folder="/movies")
    assert out["missing"] == ["quality_profile '4K' no existe"]


async def test_add_movie_error(api, call) -> None:
    api.get(f"{R}/movie/lookup").mock(side_effect=httpx.ReadTimeout("x"))
    assert "no respondió" in await call.error("add_movie", term="x")


# ------------------------------------------------------------ manual import

E04 = "/downloads/The.Capture.S03E04.1080p.WEB.H264-NTb/the.capture.s03e04.1080p.mkv"
PACK_E04 = "/downloads/The.Capture.S03.1080p.WEB.H264-PACK/The.Capture.S03E04.mkv"
PACK_E01 = "/downloads/The.Capture.S03.1080p.WEB.H264-PACK/The.Capture.S03E01.mkv"


def _scan(api, base: str, mapping: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        folder = request.url.params["folder"]
        return httpx.Response(200, json=load(mapping[folder]) if folder in mapping else [])

    return api.get(f"{base}/manualimport").mock(side_effect=handler)


async def test_manual_import_single_file(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _scan(api, S, {E04: "sonarr_manualimport_s03e04"})
    route = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("manual_import", service="sonarr", files=[E04], wait=False)
    sent = body(route)
    assert sent["name"] == "ManualImport" and sent["importMode"] == "auto"  # like the web UI: never breaks seeding
    f = sent["files"][0]
    assert f["path"] == E04 and f["seriesId"] == 1 and f["episodeIds"] == [304]
    assert f["quality"]["quality"]["name"] == "WEBDL-1080p"
    assert out["files"][0]["episodes"] == ["S03E04"]
    assert out["files"][0]["replaces_existing_file"] is False


async def test_manual_import_refuses_two_files_same_episode(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _scan(api, S, {E04: "sonarr_manualimport_s03e04", PACK_E04: "sonarr_manualimport_pack_e04"})
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("manual_import", service="sonarr", files=[E04, PACK_E04], wait=False)
    assert out["imported"] is False
    assert "mismo episodio" in out["problems"][0]["problem"]
    assert not cmd.called


async def test_manual_import_refuses_rejected_and_unknown(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _scan(api, S, {E04: "sonarr_manualimport_s03e04", PACK_E01: "sonarr_manualimport_pack_e01"})
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("manual_import", service="sonarr", files=[E04, PACK_E01, "/downloads/nope.mkv"], wait=False)
    assert out["imported"] is False and not cmd.called
    problems = {p.get("path"): p for p in out["problems"]}
    assert "Not an upgrade" in problems[PACK_E01]["rejections"][0]
    assert "no existe" in problems["/downloads/nope.mkv"]["problem"]
    assert out["ok_files"][0]["path"] == E04


async def test_manual_import_radarr_copy(api, call) -> None:
    api.get(f"{R}/queue").respond(json={"records": []})
    path = "/downloads/Past.Lives.2023.1080p.BluRay.x264-FLUX/Past.Lives.2023.1080p.mkv"
    _scan(api, R, {path: "radarr_manualimport_pastlives"})
    route = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    await call.ok("manual_import", service="radarr", files=[path], import_mode="copy", wait=False)
    sent = body(route)
    assert sent["importMode"] == "copy" and sent["files"][0]["movieId"] == 3


async def test_manual_import_error(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/manualimport").respond(401)
    assert "401" in await call.error("manual_import", service="sonarr", files=[E04])


async def test_set_monitored_episode_by_numbers(api, call) -> None:
    """One call (one permission dialog) instead of looking the episode id up first."""
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    route = api.put(f"{S}/episode/monitor").respond(json=[])
    out = await call.ok("set_monitored", monitored=False, series="The Capture", season=3, episodes=[2])
    assert body(route) == {"episodeIds": [302], "monitored": False}
    assert out["episodes"] == ["S03E02"]
    assert "[9]" in await call.error("set_monitored", monitored=False, series="The Capture", season=3, episodes=[9])
