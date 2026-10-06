from __future__ import annotations

import httpx

from arr_doctor.tools.diagnostics import find_suspicious_extensions
from tests.conftest import R, S, load


async def test_get_queue(api, call) -> None:
    route = api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    out = await call.ok("get_queue", service="sonarr")
    params = route.calls.last.request.url.params
    assert params["includeSeries"] == "true" and params["includeEpisode"] == "true"
    q = out["sonarr"]
    assert q["by_state"] == {"downloading": 1, "importBlocked": 1, "importPending": 1}
    blocked = next(i for i in q["items"] if i["id"] == 12)
    assert blocked["episode"] == "S03E04" and blocked["series"] == "The Capture"
    assert blocked["indexer"] == "LimeTorrents (Prowlarr)"
    assert blocked["download_client"] == "Download Station"
    assert "executable file" in blocked["messages"][0]


async def test_get_queue_only_problems(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{R}/queue").respond(json=load("radarr_queue"))
    out = await call.ok("get_queue", only_problems=True)
    assert {i["id"] for i in out["sonarr"]["items"]} == {12, 13}
    assert out["radarr"]["items"][0]["movie"] == "Past Lives"


async def test_get_queue_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    assert "API key incorrecta" in await call.error("get_queue", service="sonarr")


async def test_get_history_paged_with_series_filter(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    route = api.get(f"{S}/history").respond(json=load("sonarr_history"))
    out = await call.ok("get_history", series="The Capture", event_type="grabbed", limit=10)
    params = route.calls.last.request.url.params
    assert params.get_list("seriesIds") == ["1"] and params.get_list("eventType") == ["1"]
    assert params["pageSize"] == "10"
    h = out["sonarr"]
    assert "radarr" not in out
    assert h["total"] == 120 and h["truncated"] is True
    grab = next(i for i in h["items"] if i["id"] == 502)
    assert grab["indexer"] == "LimeTorrents (Prowlarr)" and grab["size"] == "2.24 GB"
    assert "guid" not in grab and "torrentInfoHash" not in grab


async def test_get_history_days_uses_since(api, call) -> None:
    route = api.get(f"{S}/history/since").respond(json=load("sonarr_history_since"))
    out = await call.ok("get_history", service="sonarr", days=7, event_type="failed")
    params = route.calls.last.request.url.params
    assert "date" in params and params["eventType"] == "4"
    assert [i["id"] for i in out["sonarr"]["items"]] == [502, 503, 501, 500]  # newest first


async def test_get_history_radarr_event_mapping(api, call) -> None:
    route = api.get(f"{R}/history").respond(json={"totalRecords": 0, "records": []})
    await call.ok("get_history", service="radarr", event_type="deleted")
    assert route.calls.last.request.url.params.get_list("eventType") == ["6"]


async def test_get_history_error(api, call) -> None:
    api.get(f"{S}/history").mock(side_effect=httpx.ReadTimeout("x"))
    assert "no respondió" in await call.error("get_history", service="sonarr")


async def test_get_blocklist(api, call) -> None:
    api.get(f"{S}/blocklist").respond(json=load("sonarr_blocklist"))
    out = await call.ok("get_blocklist", service="sonarr")
    b = out["sonarr"]
    assert b["by_indexer_in_page"] == {"TheRARBG (Prowlarr)": 1, "1337x (Prowlarr)": 1}
    assert ".scr" in b["items"][0]["reason"]


async def test_get_blocklist_error(api, call) -> None:
    api.get(f"{S}/blocklist").respond(401)
    assert "401" in await call.error("get_blocklist", service="sonarr")


async def test_get_health_includes_prowlarr(api, call) -> None:
    api.get(f"{S}/health").respond(json=load("sonarr_health"))
    api.get(f"{R}/health").respond(json=[])
    api.get("http://prowlarr.test:9696/api/v1/health").respond(401)
    out = await call.ok("get_health")
    assert out["sonarr"][0]["source"] == "DownloadClientCheck"
    assert out["radarr"] == []
    assert "401" in out["prowlarr"]["error"]


async def test_get_logs(api, call) -> None:
    route = api.get(f"{S}/log").respond(json=load("sonarr_log"))
    out = await call.ok("get_logs", service="sonarr", limit=5)
    assert route.calls.last.request.url.params["level"] == "error"
    assert out["sonarr"]["items"][0]["message"] == "Failed to get torrents"


async def test_get_logs_error(api, call) -> None:
    api.get(f"{S}/log").respond(401)
    assert "401" in await call.error("get_logs", service="sonarr")


async def test_get_disk_space(api, call) -> None:
    api.get(f"{S}/diskspace").respond(json=load("sonarr_diskspace"))
    out = await call.ok("get_disk_space", service="sonarr")
    assert out["sonarr"][0] == {"path": "/tv", "free": "1.09 TB", "total": "3.64 TB", "free_percent": 30.0}


async def test_get_disk_space_error(api, call) -> None:
    api.get(f"{S}/diskspace").mock(side_effect=httpx.ConnectError("x"))
    assert "No se pudo conectar" in await call.error("get_disk_space", service="sonarr")


async def test_get_command_status(api, call) -> None:
    api.get(f"{S}/command/1234").respond(json=load("sonarr_command_completed"))
    out = await call.ok("get_command_status", service="sonarr", command_id=1234)
    assert out["status"] == "completed" and out["result"] == "successful"


async def test_get_command_status_error(api, call) -> None:
    api.get(f"{S}/command/1").respond(404)
    assert "404" in await call.error("get_command_status", service="sonarr", command_id=1)


async def test_find_orphan_downloads_sonarr(api, call) -> None:
    scan = api.get(f"{S}/manualimport").respond(json=load("sonarr_manualimport_downloads"))
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{S}/history/since").respond(json=load("sonarr_history_since"))
    out = await call.ok("find_orphan_downloads", service="sonarr")
    params = scan.calls.last.request.url.params
    # Detected from the queue output paths (/downloads/<release>) and the import history.
    assert params["folder"] == "/downloads" and params["filterExistingFiles"] == "true"
    o = out["sonarr"]
    assert o["folders"] == ["/downloads"] and o["folders_source"] == "detected"
    assert o["scanned_files"] == 5
    assert o["tracked_by_queue"] == 1  # dbid_CCC is in the queue
    group = o["groups"]["items"][0]
    assert group["series"] == "The Capture"
    statuses = sorted(f["status"] for f in group["files"])
    assert statuses == ["duplicate", "missing", "missing"]
    assert o["episode_conflicts"] == [
        {
            "episode_id": 304,
            "files": [
                "/downloads/The.Capture.S03E04.1080p.WEB.H264-NTb/the.capture.s03e04.1080p.mkv",
                "/downloads/The.Capture.S03.1080p.WEB.H264-PACK/The.Capture.S03E04.mkv",
            ],
        }
    ]
    assert o["unmatched"]["total"] == 1


async def test_find_orphan_downloads_radarr_custom_folder(api, call) -> None:
    scan = api.get(f"{R}/manualimport").respond(json=load("radarr_manualimport_downloads"))
    api.get(f"{R}/queue").respond(json={"totalRecords": 0, "records": []})
    out = await call.ok("find_orphan_downloads", service="radarr", folder="/volume1/dl/")
    assert scan.calls.last.request.url.params["folder"] == "/volume1/dl/"
    groups = {g["movie"]: g for g in out["radarr"]["groups"]["items"]}
    assert groups["Past Lives"]["files"][0]["status"] == "missing"
    assert groups["Dune"]["files"][0]["status"] == "duplicate"
    assert out["radarr"]["unmatched"]["total"] == 1


async def test_find_orphan_downloads_error(api, call) -> None:
    api.get(f"{S}/manualimport").mock(side_effect=httpx.ReadTimeout("x"))
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{S}/history/since").respond(json=[])
    assert "no respondió en 180 s" in await call.error("find_orphan_downloads", service="sonarr")


def test_suspicious_regex() -> None:
    assert find_suspicious_extensions("Found executable file with extension: '.exe'") == ["exe"]
    assert find_suspicious_extensions("setup.SCR", "x.lnk") == ["lnk", "scr"]
    assert find_suspicious_extensions("movie.mkv", "The.Executive.2020", ".msix", "a.exe2") == []
    assert find_suspicious_extensions("pack.zipx") == ["zipx"]
    # Normalized titles as Sonarr stores them (real case: "...H264-VICE.exe").
    assert find_suspicious_extensions(titles=("Ted Lasso S04E10 1080p WEB H264 VICE exe",)) == ["exe"]
    assert find_suspicious_extensions(titles=("Show.S01E01.1080p-GRP_scr",)) == ["scr"]
    # ...but only at the end of a title, and never in free text without a dot.
    assert find_suspicious_extensions(titles=("The Exe Files S01E01 1080p",)) == []
    assert find_suspicious_extensions("ran the setup exe manually") == []


async def test_find_suspicious_releases(api, call) -> None:
    for base, kind in ((S, "sonarr"), (R, "radarr")):
        api.get(f"{base}/queue").respond(json=load(f"{kind}_queue"))
        api.get(f"{base}/history/since").respond(json=load(f"{kind}_history_since"))
    api.get(f"{S}/blocklist").respond(json=load("sonarr_blocklist"))
    api.get(f"{R}/blocklist").respond(json=load("radarr_blocklist"))
    out = await call.ok("find_suspicious_releases", days=7)
    s = out["sonarr"]
    assert [q["id"] for q in s["queue"]] == [12]
    assert s["queue"][0]["suspicious_extensions"] == ["exe"]
    assert s["queue"][0]["indexer"] == "LimeTorrents (Prowlarr)"
    assert [h["id"] for h in s["history"]] == [503]
    assert s["history"][0]["indexer"] == "TheRARBG (Prowlarr)"
    assert len(s["blocklist"]) == 1
    assert out["radarr"]["queue"][0]["movie"] == "Past Lives"
    assert out["by_indexer"] == {"TheRARBG (Prowlarr)": 2, "LimeTorrents (Prowlarr)": 1}
    assert "remove_from_queue" in out["hint"]


async def test_find_suspicious_releases_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    api.get(f"{S}/history/since").respond(json=[])
    api.get(f"{S}/blocklist").respond(json={"records": []})
    assert "401" in await call.error("find_suspicious_releases", service="sonarr")


async def test_one_service_down_does_not_hide_the_other(api, call) -> None:
    api.get(f"{S}/queue").respond(json=load("sonarr_queue"))
    api.get(f"{R}/queue").mock(side_effect=httpx.ConnectError("refused"))
    out = await call.ok("get_queue")
    assert out["sonarr"]["total"] == 3
    assert "No se pudo conectar con Radarr" in out["radarr"]["error"]


async def test_all_services_down_is_an_error(api, call) -> None:
    api.get(f"{S}/queue").respond(401)
    api.get(f"{R}/queue").respond(401)
    msg = await call.error("get_queue")
    assert "Sonarr devolvió 401" in msg and "Radarr devolvió 401" in msg


async def test_suspicious_counts_each_download_once(api, call) -> None:
    queue = load("sonarr_queue")
    history = load("sonarr_history_since")
    # A failed event for the same download that is still in the queue.
    history.append({**history[1], "id": 999, "eventType": "downloadFailed",
                    "data": {"message": "Found executable file .exe"}})
    api.get(f"{S}/queue").respond(json=queue)
    api.get(f"{S}/history/since").respond(json=history)
    api.get(f"{S}/blocklist").respond(json={"records": []})
    out = await call.ok("find_suspicious_releases", service="sonarr")
    assert out["by_indexer"]["LimeTorrents (Prowlarr)"] == 1


async def test_find_orphan_downloads_uses_env_path(api) -> None:
    from fastmcp import Client

    from arr_doctor.server import build_server
    from tests.conftest import make_settings

    scan = api.get(f"{S}/manualimport").respond(json=[])
    api.get(f"{S}/queue").respond(json={"records": []})
    async with Client(build_server(make_settings(arr_downloads_path="/data/torrents/"))) as c:
        res = await c.call_tool("find_orphan_downloads", {"service": "sonarr"})
    assert scan.calls.last.request.url.params["folder"] == "/data/torrents/"
    assert res.structured_content["sonarr"]["folders_source"] == "ARR_DOWNLOADS_PATH"


async def test_find_orphan_downloads_nothing_to_detect(api, call) -> None:
    api.get(f"{S}/queue").respond(json={"records": []})
    api.get(f"{S}/history/since").respond(json=[])
    assert "ARR_DOWNLOADS_PATH" in await call.error("find_orphan_downloads", service="sonarr")


def test_detect_download_folders() -> None:
    from arr_doctor.tools.diagnostics import detect_download_folders

    queue = [{"outputPath": "D:\\Downloads\\TV\\Show.S01E01-GRP"}, {"outputPath": "D:\\Downloads\\TV\\Other.S01E02"}]
    history = [
        # Release folder named after the release: the download folder is one level up.
        {"sourceTitle": "Show.S01E03-GRP", "data": {"droppedPath": "d:\\downloads\\tv\\Show.S01E03-GRP\\show.s01e03.mkv"}},
        # Single file directly in a different folder.
        {"sourceTitle": "Show.S01E04", "data": {"droppedPath": "\\\\nas\\media\\incoming\\Show.S01E04.mkv"}},
        # Subfolder of an already chosen folder: covered by it.
        {"sourceTitle": "X", "data": {"droppedPath": "D:\\Downloads\\TV\\sub\\x.mkv"}},
    ]
    assert detect_download_folders(queue, history) == ["D:\\Downloads\\TV", "\\\\nas\\media\\incoming"]


async def test_orphans_with_windows_paths(api, call) -> None:
    """Sonarr running on Windows: backslashes and case-insensitive paths."""
    queue = load("sonarr_queue")
    for q in queue["records"]:
        q["outputPath"] = "D:\\Downloads\\" + q["title"]
        q["downloadId"] = "other"
    scan = load("sonarr_manualimport_downloads")
    for item in scan:
        item["path"] = "d:\\downloads\\" + item["path"].removeprefix("/downloads/").replace("/", "\\")
        item.pop("downloadId", None)
    api.get(f"{S}/queue").respond(json=queue)
    route = api.get(f"{S}/manualimport").respond(json=scan)
    api.get(f"{S}/history/since").respond(json=[])
    out = await call.ok("find_orphan_downloads", service="sonarr")
    assert route.calls.last.request.url.params["folder"] == "D:\\Downloads"
    # The S03E06 file sits inside a queued item's output folder despite the different case.
    assert out["sonarr"]["tracked_by_queue"] == 1


async def test_get_queue_hides_unknown_items_by_default(api, call) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params["includeUnknownSeriesItems"] == "true":
            return httpx.Response(200, json={**load("sonarr_queue"), "totalRecords": 89})
        return httpx.Response(200, json=load("sonarr_queue"))

    route = api.get(f"{S}/queue").mock(side_effect=handler)
    out = await call.ok("get_queue", service="sonarr")
    assert out["sonarr"]["unknown_items_hidden"] == 86
    assert out["sonarr"]["total"] == 3
    params = [c.request.url.params["includeUnknownSeriesItems"] for c in route.calls]
    assert sorted(params) == ["false", "true"]

    out = await call.ok("get_queue", service="sonarr", include_unknown=True)
    assert "unknown_items_hidden" not in out["sonarr"]


def _season_pack_queue() -> dict:
    """Like a real Sonarr: one queue record per episode of a pack, same downloadId."""
    base = load("sonarr_queue")["records"][2]
    msgs = [{"title": "pack", "messages": [
        "One or more episodes expected in this release were not imported or missing from the release",
        "E01.mkv: Not an upgrade for existing episode file(s). Existing quality: WEBDL-2160p. New Quality WEBDL-1080p.",
    ]}]
    records = []
    for n in (1, 2, 3):
        ep = {**base["episode"], "id": 400 + n, "seasonNumber": 1, "episodeNumber": n}
        records.append({**base, "id": 900 + n, "episodeId": 400 + n, "episode": ep, "downloadId": "pack-1",
                         "title": "Show S01 1080p", "statusMessages": msgs})
    return {"totalRecords": 3, "records": records}


async def test_season_pack_is_one_queue_entry(api, call) -> None:
    api.get(f"{S}/queue").respond(json=_season_pack_queue())
    out = await call.ok("get_queue", service="sonarr")
    items = out["sonarr"]["items"]
    assert len(items) == 1
    assert items[0]["episodes"] == ["S01E01", "S01E02", "S01E03"] and items[0]["queue_ids"] == [901, 902, 903]
    assert "episode" not in items[0]


async def test_diagnose_season_pack_once_without_false_partial_pack(api, call) -> None:
    api.get(f"{S}/queue").respond(json=_season_pack_queue())
    scan = [{"path": f"/downloads/pack/E0{n}.mkv", "rejections": [
        {"reason": "Not an upgrade for existing episode file(s)", "type": "permanent"}]} for n in (1, 2, 3)]
    route = api.get(f"{S}/manualimport").respond(json=scan)
    out = await call.ok("diagnose_import", service="sonarr")
    assert out["checked"] == 1 and route.call_count == 1
    causes = [d["cause"] for d in out["items"][0]["diagnosis"]]
    assert causes == ["not_upgrade"]  # all files are there: nothing is "missing from the pack"
    by_id = await call.ok("diagnose_import", service="sonarr", queue_id=902)
    assert by_id["items"][0]["queue_ids"] == [901, 902, 903]
