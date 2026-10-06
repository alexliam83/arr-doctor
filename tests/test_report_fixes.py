"""Fixes from the first Claude Desktop test run (report items B1–B9)."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import R, S, load


# B1 ------------------------------------------------------------------------
async def test_only_problems_includes_stalled_downloads(api, call) -> None:
    """Radarr reports health=ok for downloads stuck since months: they are problems."""
    queue = load("radarr_queue")
    stuck = {**queue["records"][0], "id": 50, "status": "downloading", "trackedDownloadState": "downloading",
             "trackedDownloadStatus": "ok", "statusMessages": [], "size": 2e9, "sizeleft": 2e9,
             "added": "2026-07-01T00:00:00Z", "downloadId": "stuck", "title": "Stuck.Movie.2016.1080p"}
    api.get(f"{R}/queue").respond(json={"totalRecords": 1, "records": [stuck]})
    out = await call.ok("get_queue", service="radarr", only_problems=True)
    item = out["radarr"]["items"][0]
    assert item["stall_reason"] == "no_progress" and out["radarr"]["stalled"] == 1


# B2 ------------------------------------------------------------------------
def _grab(hid: int, ep_id: int, code: int, date: str, aired: str, size: str, indexer: str) -> dict:
    ep = {**load("sonarr_episodes_s3")[0], "id": ep_id, "episodeNumber": code, "airDateUtc": aired}
    return {"id": hid, "episodeId": ep_id, "seriesId": 1, "sourceTitle": f"Show S03E0{code} 1080p WEB",
            "date": date, "downloadId": f"d{hid}", "eventType": "grabbed", "episode": ep,
            "series": {"title": "Lioness"}, "quality": {}, "data": {"indexer": indexer, "size": size}}


async def test_pre_release_grabs_and_identical_sizes(api, call) -> None:
    """Real case: episodes grabbed 12 days before airing, several with the same 917.95 MB."""
    history = [
        _grab(1, 101, 3, "2026-09-01T10:00:00Z", "2026-09-13T04:00:00Z", "962538291", "LimeTorrents (Prowlarr)"),
        _grab(2, 102, 4, "2026-09-01T10:01:00Z", "2026-09-20T04:00:00Z", "962538291", "LimeTorrents (Prowlarr)"),
        # A release a few hours before the official air time is normal: not flagged.
        _grab(3, 103, 5, "2026-09-26T22:00:00Z", "2026-09-27T04:00:00Z", "1500000000", "1337x (Prowlarr)"),
    ]
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/history/since").respond(json=history)
    api.get(f"{S}/blocklist").respond(json={"records": []})
    out = await call.ok("find_suspicious_releases", service="sonarr", days=60)
    pre = out["sonarr"]["pre_release_grabs"]
    assert [p["episode"] for p in pre] == ["S03E03", "S03E04"]
    assert pre[0]["days_before_release"] == 11.8
    same = out["sonarr"]["identical_size_grabs"][0]
    assert same["episodes"] == ["S03E03", "S03E04"] and same["indexers"] == ["LimeTorrents (Prowlarr)"]
    assert {p["likely"] for p in pre} == {"fake"}  # never imported
    assert out["sonarr"]["likely_fakes_by_indexer"] == {"LimeTorrents (Prowlarr)": 2}
    assert "by_indexer" not in out or out["by_indexer"] == {}  # that count is for executables


async def test_early_release_that_imported_is_not_called_fake(api, call) -> None:
    """Real case: a whole season released on a streaming service before the air dates."""
    grab = _grab(1, 101, 3, "2026-10-03T10:00:00Z", "2026-10-13T04:00:00Z", "540000000", "LimeTorrents (Prowlarr)")
    imported = {**grab, "id": 2, "eventType": "downloadFolderImported", "date": "2026-10-03T11:00:00Z"}
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/history/since").respond(json=[grab, imported])
    api.get(f"{S}/blocklist").respond(json={"records": []})
    out = await call.ok("find_suspicious_releases", service="sonarr")
    assert out["sonarr"]["pre_release_grabs"][0]["likely"] == "early_release"
    assert "likely_fakes_by_indexer" not in out["sonarr"]


async def test_season_pack_is_not_an_identical_size_group(api, call) -> None:
    """A season pack is one download recorded once per episode with the pack size."""
    pack = [{**_grab(i, 100 + i, i, "2026-09-01T10:00:00Z", "2026-08-01T00:00:00Z", "12000000000", "TPB"),
             "downloadId": "pack"} for i in (1, 2, 3)]
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/history/since").respond(json=pack)
    api.get(f"{S}/blocklist").respond(json={"records": []})
    out = await call.ok("find_suspicious_releases", service="sonarr")
    assert "identical_size_grabs" not in out["sonarr"]


async def test_movie_grabbed_before_digital_release(api, call) -> None:
    movie = {**load("radarr_movie_3"), "digitalRelease": "2026-12-01T00:00:00Z", "physicalRelease": None}
    grab = {**load("radarr_history_since")[0], "date": "2026-10-01T00:00:00Z", "movie": movie}
    api.get(f"{R}/queue").respond(json={"records": []})
    api.get(f"{R}/history/since").respond(json=[grab])
    api.get(f"{R}/blocklist").respond(json={"records": []})
    out = await call.ok("find_suspicious_releases", service="radarr")
    assert out["radarr"]["pre_release_grabs"][0]["movie"] == "Past Lives"


# B5 ------------------------------------------------------------------------
def test_other_episode_results_are_grouped() -> None:
    from arr_doctor.i18n import set_language
    from arr_doctor.tools.troubleshoot import summarize_releases

    set_language("en")
    rel = lambda rej: {"approved": False, "rejections": rej, "indexer": "x"}  # noqa: E731
    releases = [rel(["Episode wasn't requested: 1x02"]), rel(["Wrong season"]), rel(["Unknown Series"]),
                rel(["Release is 9 GB, larger than maximum 4 GB"])]
    out = summarize_releases(releases, 5)
    reasons = {r["reason"]: r["releases"] for r in out["rejection_reasons"]}
    assert reasons["Release is 9 GB, larger than maximum 4 GB"] == 1
    assert reasons["Results for other episodes, seasons or series (not relevant here)"] == 3
    assert len(out["closest_rejected"]) == 1


# B6 ------------------------------------------------------------------------
async def test_search_after_explain_points_to_its_results(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    ep = {**load("sonarr_episodes_s3")[3], "lastSearchTime": datetime.now(UTC).isoformat()}
    api.get(f"{S}/episode").respond(json=[ep])
    api.get(f"{S}/release").respond(json=load("sonarr_releases_s03e04"))
    await call.ok("explain_search", series="The Capture", season=3, episode=4)
    cmd = api.post(f"{S}/command").respond(json={})
    out = await call.ok("search_episodes", episode_ids=[304])
    assert out["searched"] is False and "grab_release" in out["message"] and not cmd.called


# B9 ------------------------------------------------------------------------
async def test_fuzzy_title_matching_is_stricter(api, call) -> None:
    series = load("sonarr_series_list")
    series.append({**series[0], "id": 9, "title": "The Curse", "alternateTitles": []})
    series.append({**series[0], "id": 10, "title": "Black Bird", "alternateTitles": []})
    api.get(f"{S}/series").respond(json=series)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    msg = await call.error("get_series", series="The Ofice")
    assert "The Curse" not in msg  # used to be suggested because of the shared "The"
    out = await call.ok("get_series", series="Bird")
    assert out["title"] == "Black Bird"  # whole-word match still works
    out = await call.ok("get_series", series="Captu")
    assert out["title"] == "The Capture"  # and so does a cut-short last word
