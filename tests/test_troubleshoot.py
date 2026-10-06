from __future__ import annotations

import json

import httpx

from arr_doctor.i18n import set_language
from arr_doctor.tools.troubleshoot import diagnose, quality_ranks, upgrade_verdict
from tests.conftest import R, S, load


def _series(api) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))


# ------------------------------------------------------------ explain_search


async def test_explain_search_groups_rejections(api, call) -> None:
    _series(api)
    route = api.get(f"{S}/release").respond(json=load("sonarr_releases_s03e04"))
    out = await call.ok("explain_search", series="The Capture", season=3, episode=4)
    assert route.calls.last.request.url.params["episodeId"] == "304"
    assert out["episode"] == "S03E04" and out["total"] == 6
    assert out["approved"] == 1 and out["rejected"] == 5
    reasons = {r["reason"]: r["releases"] for r in out["rejection_reasons"]}
    # Size rejections with different numbers are grouped together.
    assert reasons["Language is not wanted in profile"] == 2
    assert reasons["Release is 14.2 GB, larger than maximum 8 GB"] == 2
    best = out["best_approved"][0]
    assert best["guid"] == "https://indexer.example/t/1" and best["indexer_id"] == 1 and best["cf_score"] == 10
    # Temporarily rejected releases are the nearest misses.
    assert out["closest_rejected"][0]["title"].endswith("HDTV.x264-OLD")
    assert "grab_release" in out["note"]
    assert "checks" not in out  # nothing to warn about


async def test_explain_search_season_and_checks(api, call) -> None:
    series = load("sonarr_series_list")
    series[0]["monitored"] = False
    api.get(f"{S}/series").respond(json=series)
    route = api.get(f"{S}/release").respond(json=[])
    out = await call.ok("explain_search", series="The Capture", season=3)
    params = route.calls.last.request.url.params
    assert params["seriesId"] == "1" and params["seasonNumber"] == "3"
    assert any("no está monitorizada" in c for c in out["checks"])
    assert any("indexers no devolvieron nada" in c for c in out["checks"])
    assert out["total"] == 0


async def test_explain_search_future_episode(api, call) -> None:
    _series(api)
    api.get(f"{S}/release").respond(json=[])
    out = await call.ok("explain_search", series="The Capture", season=3, episode=5)
    assert any("Aún no se ha emitido" in c for c in out["checks"])


async def test_explain_search_movie(api, call) -> None:
    movies = load("radarr_movie_list")
    movies[2]["isAvailable"] = False
    api.get(f"{R}/movie").respond(json=movies)
    route = api.get(f"{R}/release").respond(json=[])
    out = await call.ok("explain_search", movie="Past Lives")
    assert route.calls.last.request.url.params["movieId"] == "3"
    assert any("disponibilidad mínima" in c for c in out["checks"])


async def test_explain_search_needs_target(api, call) -> None:
    assert "Indica `series` o `movie`" in await call.error("explain_search")


async def test_explain_search_error(api, call) -> None:
    _series(api)
    api.get(f"{S}/release").mock(side_effect=httpx.ReadTimeout("x"))
    assert "no respondió en 120 s" in await call.error("explain_search", series="The Capture", season=3, episode=4)


async def test_grab_release(api, call) -> None:
    route = api.post(f"{S}/release").respond(json=load("sonarr_releases_s03e04")[3])
    out = await call.ok("grab_release", service="sonarr", guid="https://indexer.example/t/4", indexer_id=1)
    assert json.loads(route.calls.last.request.content) == {"guid": "https://indexer.example/t/4", "indexerId": 1}
    assert out["grabbed"] is True and out["release"]["quality"] == "WEBDL-2160p"


async def test_grab_release_expired(api, call) -> None:
    api.post(f"{S}/release").respond(404, json={"message": "Couldn't find requested release in cache, try searching again"})
    assert "try searching again" in await call.error("grab_release", service="sonarr", guid="g", indexer_id=1)


# ------------------------------------------------------------ diagnose_import


def test_diagnose_rules() -> None:
    assert diagnose(["Caution: Found executable file with extension: '.exe'"]) == ["dangerous"]
    assert diagnose(["Not an upgrade for existing episode file(s)"]) == ["not_upgrade"]
    assert diagnose(["Found matching series via grab history, but release was matched to series by ID. Automatic import is not possible"]) == ["unknown_match"]
    assert diagnose(["Access to the path '/tv/x' is denied."]) == ["permissions"]
    assert diagnose(["Sample"]) == ["sample"]
    assert diagnose(["One or more episodes expected in the release were not imported or missing"]) == ["partial_pack"]
    assert diagnose(["Import failed, path does not exist or is not accessible by Sonarr: /volume1/x"]) == ["path_missing"]
    assert diagnose(["all good"]) == []


async def test_diagnose_import_dangerous(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{S}/manualimport").respond(json=[])
    out = await call.ok("diagnose_import", service="sonarr", queue_id=12)
    diag = out["items"][0]["diagnosis"]
    assert diag[0]["cause"] == "dangerous"
    assert "blocklist=true" in diag[0]["fix"]
    # A dangerous release with no video is not reported as a path problem.
    assert all(d["cause"] != "path_not_visible" for d in diag)


async def test_diagnose_import_not_upgrade_with_scan(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    scan = api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_pack_e01"))
    out = await call.ok("diagnose_import", service="sonarr", queue_id=13)
    assert scan.calls.last.request.url.params["downloadId"] == "dbid_CCC"
    item = out["items"][0]
    assert item["diagnosis"][0]["cause"] == "not_upgrade"
    assert item["files"][0]["rejections"]


async def test_diagnose_import_path_not_visible(api, call) -> None:
    queue = load("sonarr_queue")
    queue["records"][2]["statusMessages"] = []
    api.get(f"{S}/queue").respond(json=queue)
    api.get(f"{S}/manualimport").respond(json=[])
    out = await call.ok("diagnose_import", service="sonarr", queue_id=13)
    first = out["items"][0]["diagnosis"][0]
    assert first["cause"] == "path_not_visible" and "/downloads/The.Capture.S03E06" in first["explanation"]


async def test_diagnose_import_all_stuck_items(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{S}/manualimport").respond(json=[])
    out = await call.ok("diagnose_import", service="sonarr")
    assert out["checked"] == 2  # ids 12 and 13; 11 is downloading fine


async def test_diagnose_import_unknown_id(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    assert "id 99" in await call.error("diagnose_import", service="sonarr", queue_id=99)


async def test_diagnose_import_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    assert "401" in await call.error("diagnose_import", service="sonarr")


# --------------------------------------------------------------- check_paths


async def test_check_paths(api, call) -> None:
    api.get(f"{S}/rootfolder").respond(json=[{"id": 1, "path": "/tv", "accessible": False, "freeSpace": 0}])
    api.get(f"{S}/remotepathmapping").respond(json=load("sonarr_remotepathmapping"))
    api.get(f"{S}/downloadclient").respond(json=load("sonarr_downloadclient"))
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{S}/health").respond(json=load("sonarr_health_paths"))
    api.get(f"{S}/manualimport").respond(json=[])
    out = await call.ok("check_paths", service="sonarr")
    s = out["sonarr"]
    assert s["ok"] is False
    assert s["remote_path_mappings"][0]["local_path"] == "/downloads/"
    dc = s["download_clients"][0]
    assert dc["host"] == "192.0.2.10" and dc["category"] == "tv" and "password" not in json.dumps(dc)
    assert s["download_output_folders"] == [{"path": "/downloads", "visible": False}]
    causes = {p["cause"] for p in s["problems"]}
    assert causes == {"path_not_visible", "root_inaccessible"}
    assert [h["source"] for h in s["health"]] == ["RemotePathMappingCheck"]


async def test_check_paths_error(api, call) -> None:
    for path in ("rootfolder", "remotepathmapping", "downloadclient", "queue", "health"):
        api.get(f"{S}/{path}").respond(401)
    assert "401" in await call.error("check_paths", service="sonarr")


# ---------------------------------------------------- find_stalled_downloads


async def test_find_stalled_downloads(api, call) -> None:
    queue = load("sonarr_queue_stalled")
    recs = {q["id"]: q for q in queue["records"]}
    recs[33]["timeleft"] = "01:00:00"  # half done and moving: fine
    old = "2026-01-01T00:00:00Z"
    # Downloading for months, 99 % done, no speed (no ETA): no_activity.
    queue["records"].append({**recs[33], "id": 36, "sizeleft": 1e6, "timeleft": None, "added": old, "downloadId": "d36"})
    # Magnet without metadata, no "added": age comes from the grab history.
    queue["records"].append({**recs[33], "id": 37, "size": 0, "sizeleft": 0, "added": None, "downloadId": "d37"})
    # Paused: waiting on purpose, never reported.
    queue["records"].append({**recs[32], "id": 38, "status": "paused", "downloadId": "d38"})
    api.get(f"{S}/queue").respond(json=queue)
    hist = api.get(f"{S}/history/since").respond(json=[{"downloadId": "d37", "date": old, "eventType": "grabbed"}])
    out = await call.ok("find_stalled_downloads", service="sonarr", min_hours=6)
    by = {i["id"]: i for i in out["sonarr"]["stalled"]}
    assert set(by) == {31, 32, 36, 37}
    assert by[31]["stall_reason"] == "stalled" and by[31]["progress_percent"] == 25.0
    assert by[32]["stall_reason"] == "no_progress" and by[32]["progress_percent"] == 0.0
    assert by[36]["stall_reason"] == "no_activity"
    assert by[37]["stall_reason"] == "no_metadata" and by[37]["age_hours"] > 1000
    assert hist.calls.last.request.url.params["eventType"] == "1"
    assert "blocklist=true" in out["hint"]


async def test_find_stalled_recent_magnet_is_not_reported(api, call) -> None:
    from datetime import UTC, datetime

    queue = load("sonarr_queue_stalled")
    recent = {**queue["records"][1], "id": 40, "size": 0, "sizeleft": 0, "added": datetime.now(UTC).isoformat()}
    api.get(f"{S}/queue").respond(json={"records": [recent]})
    out = await call.ok("find_stalled_downloads", service="sonarr", min_hours=6)
    assert out["sonarr"]["stalled"] == []


async def test_find_stalled_downloads_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    assert "401" in await call.error("find_stalled_downloads", service="sonarr")


# ------------------------------------------------------------- parse_release


def test_quality_ranks_groups() -> None:
    ranks, allowed = quality_ranks(load("sonarr_qualityprofile_full")[0])
    assert ranks[4] == 0 and ranks[3] == 1 and ranks[1003] == 1 and ranks[18] == 2
    assert allowed == {4, 3}


def test_upgrade_verdicts() -> None:
    set_language("en")
    p = load("sonarr_qualityprofile_full")[0]
    assert upgrade_verdict(p, 18, 0, 3, 0)["verdict"] == "rejected"  # 2160p not allowed
    assert upgrade_verdict(p, 3, 0, None, None)["verdict"] == "wanted"
    assert upgrade_verdict(p, 3, 0, 4, 0)["verdict"] == "upgrade"  # 720p -> 1080p
    assert upgrade_verdict(p, 4, 50, 3, 0)["verdict"] == "not_upgrade"  # worse quality
    assert upgrade_verdict(p, 3, 40, 3, 10)["verdict"] == "upgrade"  # same quality, better CF
    assert upgrade_verdict(p, 3, 10, 3, 10)["verdict"] == "not_upgrade"
    assert upgrade_verdict(p, 3, 500, 3, 100)["verdict"] == "not_upgrade"  # CF cutoff met
    assert upgrade_verdict({**p, "minFormatScore": 20}, 3, 10, None, None)["verdict"] == "rejected"


async def test_parse_release_sonarr_upgrade(api, call) -> None:
    route = api.get(f"{S}/parse").respond(json=load("sonarr_parse_s03e01_proper"))

    def episodes(request: httpx.Request) -> httpx.Response:
        # Like the real API: the file is only included when asked for.
        eps = load("sonarr_episode_301_with_file")
        if request.url.params.get("includeEpisodeFile") != "true":
            eps = [{k: v for k, v in e.items() if k != "episodeFile"} for e in eps]
        return httpx.Response(200, json=eps)

    api.get(f"{S}/episode").mock(side_effect=episodes)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile_full"))
    out = await call.ok("parse_release", title="The.Capture.S03E01.1080p.WEB.H264-FLUX")
    assert route.calls.last.request.url.params["title"] == "The.Capture.S03E01.1080p.WEB.H264-FLUX"
    assert out["service"] == "sonarr"
    assert out["matched_episodes"] == ["S03E01"]
    assert out["cf_score"] == 40 and out["existing_file"]["cf_score"] == 10
    assert out["estimate"]["verdict"] == "upgrade"


async def test_parse_release_unknown_series(api, call) -> None:
    api.get(f"{S}/parse").respond(json=load("sonarr_parse_unknown"))
    out = await call.ok("parse_release", title="Some.Other.Show.S01E01.720p", service="sonarr")
    assert out["parsed"]["series_title"] == "Some Other Show"
    assert "ninguna serie" in out["note"]


async def test_parse_release_movie_guesses_radarr(api, call) -> None:
    api.get(f"{R}/parse").respond(json=load("radarr_parse_dune_2160"))
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_1_full"))
    api.get(f"{R}/qualityprofile").respond(json=load("radarr_qualityprofile_full"))
    out = await call.ok("parse_release", title="Dune.2021.2160p.UHD.BluRay.x265-GRP")
    assert out["service"] == "radarr"
    assert out["existing_file"]["quality"] == "Bluray-1080p"
    # Existing Bluray-1080p already meets the cutoff (id 7).
    assert out["estimate"]["verdict"] == "not_upgrade"


async def test_parse_release_error(api, call) -> None:
    api.get(f"{S}/parse").respond(401)
    assert "401" in await call.error("parse_release", title="x.S01E01", service="sonarr")


# ------------------------------------------------- manual_import with matches

UNK = "/downloads/Capture.2019.3x04.mkv"


async def test_manual_import_unknown_without_match_fails(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_unknown"))
    out = await call.ok("manual_import", service="sonarr", files=[UNK], wait=False)
    assert out["imported"] is False and out["problems"][0]["problem"] == "rechazado"


async def test_manual_import_with_match(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _series(api)
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_unknown"))
    reprocess = api.post(f"{S}/manualimport").respond(json=load("sonarr_manualimport_reprocess_ok"))
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok(
        "manual_import", service="sonarr", files=[UNK],
        matches=[{"path": UNK, "series": "The Capture", "season": 3, "episodes": [4]}],
    wait=False,
    )
    sent = json.loads(reprocess.calls.last.request.content)[0]
    assert sent["seriesId"] == 1 and sent["episodeIds"] == [304] and sent["seasonNumber"] == 3
    f = json.loads(cmd.calls.last.request.content)["files"][0]
    assert f["seriesId"] == 1 and f["episodeIds"] == [304]
    assert out["files"][0]["manual_match"] is True and out["files"][0]["episodes"] == ["S03E04"]


async def test_manual_import_match_revalidated_and_rejected(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _series(api)
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_unknown"))
    api.post(f"{S}/manualimport").respond(json=load("sonarr_manualimport_reprocess_rejected"))
    cmd = api.post(f"{S}/command").respond(json={})
    out = await call.ok(
        "manual_import", service="sonarr", files=[UNK],
        matches=[{"path": UNK, "series": 1 and "The Capture", "season": 3, "episodes": [4]}],
    )
    assert out["imported"] is False and not cmd.called
    assert "Not an upgrade" in out["problems"][0]["rejections"][0]


async def test_manual_import_match_bad_episode(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    _series(api)
    api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_unknown"))
    out = await call.ok(
        "manual_import", service="sonarr", files=[UNK],
        matches=[{"path": UNK, "series": "The Capture", "season": 3, "episodes": [9]}],
    )
    assert "S03E09" in out["problems"][0]["problem"]


async def test_manual_import_match_for_unlisted_file(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    msg = await call.error(
        "manual_import", service="sonarr", files=[UNK], matches=[{"path": "/other.mkv", "movie": 1}]
    )
    assert "/other.mkv" in msg


async def test_manual_import_radarr_match(api, call) -> None:
    api.get(f"{R}/queue").respond(json={"records": []})
    path = "/downloads/The.Capture.S03E04.1080p.WEB.H264-NTb/the.capture.s03e04.1080p.mkv"
    api.get(f"{R}/manualimport").respond(json=[load("radarr_manualimport_downloads")[2]])
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    movie = load("radarr_movie_list")[2]
    reprocess = api.post(f"{R}/manualimport").respond(
        json=[{"path": path, "movieId": 3, "movie": movie, "quality": {}, "languages": [], "rejections": []}]
    )
    api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    out = await call.ok(
        "manual_import", service="radarr", files=[path], matches=[{"path": path, "movie": "Past Lives"}], wait=False
    )
    assert json.loads(reprocess.calls.last.request.content)[0]["movieId"] == 3
    assert out["files"][0]["movie"] == "Past Lives (2023)"
