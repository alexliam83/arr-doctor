from __future__ import annotations

import json

from tests.conftest import R, S, load


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _sonarr(api, recycle_bin: str = "") -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/episode").respond(json=load("sonarr_episodes_s3"))
    api.get(f"{S}/config/mediamanagement").respond(json={"recycleBin": recycle_bin})


def _deletes(api) -> dict[int, object]:
    return {fid: api.delete(f"{S}/episodefile/{fid}").respond(200) for fid in (101, 102, 103)}


async def test_preview_lists_files_and_deletes_nothing(api, call) -> None:
    _sonarr(api)
    deletes = _deletes(api)
    out = await call.ok("preview_delete_files", series="The Capture", season=3)
    assert out["total"] == 3 and out["scope"] == "S03"
    assert out["items"][0]["episodes"] == ["S03E01"] and out["items"][0]["size"]
    assert out["total_size"] and out["confirmation_token"]
    assert "para siempre" in out["recycle_bin"]
    assert not any(r.called for r in deletes.values())


async def test_delete_without_token_deletes_nothing(api, call) -> None:
    _sonarr(api)
    deletes = _deletes(api)
    out = await call.ok("delete_files", series="The Capture", season=3)
    assert out["deleted"] == 0 and "preview_delete_files" in out["note"]
    bad = await call.ok("delete_files", series="The Capture", season=3, confirmation_token="wrong")
    assert bad["deleted"] == 0
    assert not any(r.called for r in deletes.values())


async def test_delete_season_with_token_unmonitors(api, call) -> None:
    _sonarr(api, recycle_bin="/volume1/recycle")
    deletes = _deletes(api)
    monitor = api.put(f"{S}/episode/monitor").respond(json=[])
    preview = await call.ok("preview_delete_files", series="The Capture", season=3)
    out = await call.ok("delete_files", series="The Capture", season=3,
                        confirmation_token=preview["confirmation_token"])
    assert all(r.called for r in deletes.values())
    assert out["deleted"] == 3 and out["freed"]
    assert body(monitor) == {"episodeIds": [301, 302, 303], "monitored": False}
    assert out["unmonitored"] == ["S03E01", "S03E02", "S03E03"]
    assert "/volume1/recycle" in out["recycle_bin"]


async def test_token_is_tied_to_the_selection(api, call) -> None:
    _sonarr(api)
    deletes = _deletes(api)
    preview = await call.ok("preview_delete_files", series="The Capture", season=3, episodes=[2])
    out = await call.ok("delete_files", series="The Capture", season=3,
                        confirmation_token=preview["confirmation_token"])
    assert out["deleted"] == 0 and not any(r.called for r in deletes.values())


async def test_delete_some_episodes_keep_monitored(api, call) -> None:
    _sonarr(api)
    deletes = _deletes(api)
    monitor = api.put(f"{S}/episode/monitor").respond(json=[])
    preview = await call.ok("preview_delete_files", series="The Capture", season=3, episodes=[2])
    assert preview["total"] == 1
    out = await call.ok("delete_files", series="The Capture", season=3, episodes=[2], unmonitor=False,
                        confirmation_token=preview["confirmation_token"])
    assert deletes[102].called and not deletes[101].called and not deletes[103].called
    assert out["deleted"] == 1 and not monitor.called and "volverá a descargar" in out["note"]


async def test_partial_failure_only_unmonitors_deleted(api, call) -> None:
    _sonarr(api)
    api.delete(f"{S}/episodefile/101").respond(200)
    api.delete(f"{S}/episodefile/102").respond(500, json={"message": "Access denied"})
    api.delete(f"{S}/episodefile/103").respond(200)
    monitor = api.put(f"{S}/episode/monitor").respond(json=[])
    preview = await call.ok("preview_delete_files", series="The Capture", season=3)
    out = await call.ok("delete_files", series="The Capture", season=3,
                        confirmation_token=preview["confirmation_token"])
    assert out["deleted"] == 2 and out["failed"][0]["file_id"] == 102
    assert "Access denied" in out["failed"][0]["error"]
    assert body(monitor)["episodeIds"] == [301, 303]


async def test_nothing_on_disk(api, call) -> None:
    _sonarr(api)
    out = await call.ok("preview_delete_files", series="The Capture", season=3, episodes=[4, 5])
    assert out["total"] == 0 and "nada que borrar" in out["message"]
    out = await call.ok("delete_files", series="The Capture", season=3, episodes=[4, 5])
    assert out["deleted"] == 0


async def test_episodes_need_season(api, call) -> None:
    _sonarr(api)
    assert "season" in await call.error("preview_delete_files", series="The Capture", episodes=[1])


async def test_unknown_season(api, call) -> None:
    _sonarr(api)
    assert "temporada 9" in await call.error("preview_delete_files", series="The Capture", season=9)


async def test_delete_movie(api, call) -> None:
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_1_full"))
    api.get(f"{R}/config/mediamanagement").respond(json={"recycleBin": ""})
    delete = api.delete(f"{R}/moviefile/10").respond(200)
    editor = api.put(f"{R}/movie/editor").respond(json=[])
    preview = await call.ok("preview_delete_files", movie=1)
    assert preview["total"] == 1 and preview["items"][0]["path"].endswith("Dune (2021).mkv")
    assert not delete.called
    out = await call.ok("delete_files", movie=1, confirmation_token=preview["confirmation_token"])
    assert delete.called and out["deleted"] == 1 and out["unmonitored"] is True
    assert body(editor) == {"movieIds": [1], "monitored": False}


async def test_delete_error(api, call) -> None:
    api.get(f"{S}/series").respond(401)
    assert "401" in await call.error("preview_delete_files", series="The Capture", season=3)
