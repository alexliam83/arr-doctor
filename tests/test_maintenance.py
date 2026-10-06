from __future__ import annotations

import json

import httpx

from tests.conftest import R, S, load


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _library(api) -> None:
    series = load("sonarr_series_list")
    series[1]["status"] = "ended"  # The Office (2005): ended and complete
    series[1]["ended"] = True
    series[1]["monitored"] = False
    series[2]["tags"] = [2]
    api.get(f"{S}/series").respond(json=series)
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    api.get(f"{S}/tag").respond(json=load("sonarr_tags"))


# ------------------------------------------------------------ library_report


async def test_library_report_sonarr(api, call) -> None:
    _library(api)
    api.get(f"{S}/rootfolder").respond(json=load("sonarr_rootfolder"))
    out = await call.ok("library_report", service="sonarr", limit=2)
    r = out["sonarr"]
    assert r["items"] == 4 and len(r["biggest"]) == 2
    assert r["biggest"][0]["title"] == "24"  # 24 episodes on disk
    assert r["unmonitored_with_files"]["count"] == 1
    assert r["ended_and_complete"]["top"][0]["title"] == "The Office"
    assert r["missing_episodes_monitored"] == 1  # The Capture S03E04
    assert r["root_folders"][0]["path"] == "/tv"


async def test_library_report_radarr(api, call) -> None:
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    api.get(f"{R}/rootfolder").respond(json=load("radarr_rootfolder"))
    out = await call.ok("library_report", service="radarr")
    r = out["radarr"]
    assert r["items_with_files"] == 2
    assert r["by_quality"] == [{"quality": "Bluray-1080p", "movies": 2, "size": "14.90 GB"}]
    assert r["missing_monitored"] == 2


async def test_library_report_error(api, call) -> None:
    api.get(f"{S}/series").respond(401)
    api.get(f"{S}/rootfolder").respond(json=[])
    assert "401" in await call.error("library_report", service="sonarr")


# ------------------------------------------------------------------ rename


async def test_preview_rename_series_season(api, call) -> None:
    api.get(f"{S}/config/naming").respond(json={"renameEpisodes": True, "renameMovies": True})
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    route = api.get(f"{S}/rename").respond(json=load("sonarr_rename_s03"))
    out = await call.ok("preview_rename", series="The Capture", season=3)
    assert route.calls.last.request.url.params["seasonNumber"] == "3"
    assert out["total"] == 2 and out["items"][0]["to"].startswith("Season 03/The Capture - S03E01")


async def test_rename_files_series(api, call) -> None:
    api.get(f"{S}/config/naming").respond(json={"renameEpisodes": True, "renameMovies": True})
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/rename").respond(json=load("sonarr_rename_s03"))
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    preview = await call.ok("preview_rename", series="The Capture", season=3)
    assert preview["total"] == 2 and preview["confirmation_token"] and not cmd.called
    out = await call.ok("rename_files", series="The Capture", season=3,
                        confirmation_token=preview["confirmation_token"])
    assert body(cmd) == {"name": "RenameFiles", "seriesId": 1, "files": [101, 102]}
    assert out["files"] == 2 and out["command_id"] == 1234


async def test_rename_files_movie(api, call) -> None:
    api.get(f"{R}/config/naming").respond(json={"renameEpisodes": True, "renameMovies": True})
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_list")[0])
    api.get(f"{R}/rename").respond(json=load("radarr_rename_dune"))
    cmd = api.post(f"{R}/command").respond(json=load("radarr_command_queued"))
    await call.ok("rename_files", movie=1)
    assert body(cmd) == {"name": "RenameFiles", "movieId": 1, "files": [10]}


async def test_rename_files_nothing_to_do(api, call) -> None:
    api.get(f"{R}/config/naming").respond(json={"renameEpisodes": True, "renameMovies": True})
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_list")[0])
    api.get(f"{R}/rename").respond(json=[])
    cmd = api.post(f"{R}/command").respond(json={})
    out = await call.ok("rename_files", movie=1)
    assert out["renamed"] == 0 and not cmd.called


async def test_preview_rename_error(api, call) -> None:
    api.get(f"{R}/config/naming").respond(json={"renameEpisodes": True, "renameMovies": True})
    api.get(f"{R}/movie/1").respond(json=load("radarr_movie_list")[0])
    api.get(f"{R}/rename").respond(500, json={"message": "boom"})
    assert "500" in await call.error("preview_rename", movie=1)


# --------------------------------------------------------------- bulk_edit


async def test_bulk_edit_preview_does_not_write(api, call) -> None:
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    out = await call.ok("bulk_edit_preview", service="sonarr", status="ended", complete=True, set_monitored=False)
    assert out["applied"] is False and out["matched"] == 1
    assert out["items"]["items"][0]["title"] == "The Office"
    assert "bulk_edit_apply" in out["note"]
    assert not put.called


async def test_bulk_edit_apply_profile_and_tags(api, call) -> None:
    _library(api)
    new_tag = api.post(f"{S}/tag").respond(json={"id": 3, "label": "uk"})
    put = api.put(f"{S}/series/editor").respond(json={})
    args = dict(service="sonarr", items=["The Office (2001)", 1], set_quality_profile="HD - 720p/1080p",
                add_tags=["uk", "Kids"], remove_tags=["anime", "unknown"])
    preview = await call.ok("bulk_edit_preview", **args)
    out = await call.ok("bulk_edit_apply", **args, confirmation_token=preview["confirmation_token"])
    assert out["applied"] is True and out["matched"] == 2
    assert body(new_tag) == {"label": "uk"}
    first, second = (json.loads(c.request.content) for c in put.calls)
    assert sorted(first["seriesIds"]) == [1, 3]
    assert first["qualityProfileId"] == 6 and first["tags"] == [3, 2] and first["applyTags"] == "add"
    assert second == {"seriesIds": first["seriesIds"], "tags": [1], "applyTags": "remove"}


async def test_bulk_edit_radarr_filters(api, call) -> None:
    api.get(f"{R}/movie").respond(json=load("radarr_movie_list"))
    api.get(f"{R}/qualityprofile").respond(json=load("radarr_qualityprofile"))
    api.get(f"{R}/tag").respond(json=[])
    put = api.put(f"{R}/movie/editor").respond(json={})
    args = dict(service="radarr", year_from=2019, complete=False, set_minimum_availability="announced")
    preview = await call.ok("bulk_edit_preview", **args)
    out = await call.ok("bulk_edit_apply", **args, confirmation_token=preview["confirmation_token"])
    assert out["matched"] == 1  # Past Lives (2023) has no file
    assert body(put) == {"movieIds": [3], "minimumAvailability": "announced"}


async def test_bulk_edit_requires_selection_and_change(api, call) -> None:
    assert "Indica qué editar" in await call.error("bulk_edit_preview", service="sonarr", set_monitored=True)
    assert "al menos un cambio" in await call.error("bulk_edit_preview", service="sonarr", monitored=True)
    assert "solo se aplica a Radarr" in await call.error(
        "bulk_edit_preview", service="sonarr", monitored=True, set_minimum_availability="released"
    )


async def test_bulk_edit_unknown_profile(api, call) -> None:
    _library(api)
    assert "no existe" in await call.error("bulk_edit_preview", service="sonarr", monitored=True, set_quality_profile="8K")


async def test_bulk_edit_ambiguous_item(api, call) -> None:
    _library(api)
    out = await call.ok("bulk_edit_preview", service="sonarr", items=["The Office"], set_monitored=True)
    assert out["ambiguous"] is True


# ------------------------------------------------- download clients / health


async def test_test_download_clients(api, call) -> None:
    api.get(f"{S}/downloadclient").respond(json=load("sonarr_downloadclient"))
    api.post(f"{S}/downloadclient/testall").respond(400, json=load("sonarr_downloadclient_testall"))
    out = await call.ok("test_download_clients", service="sonarr")
    r = out["sonarr"]
    assert r["failing"] == 1 and r["results"][0]["name"] == "Download Station"
    assert "Unable to connect" in r["results"][0]["errors"][0]


async def test_test_download_clients_error(api, call) -> None:
    api.get(f"{S}/downloadclient").respond(401)
    api.post(f"{S}/downloadclient/testall").respond(401)
    assert "401" in await call.error("test_download_clients", service="sonarr")


async def test_health_includes_fix(api, call) -> None:
    api.get(f"{S}/health").respond(json=load("sonarr_health") + [{"source": "SomethingNew", "type": "warning", "message": "x"}])
    out = await call.ok("get_health", service="sonarr")
    known, unknown = out["sonarr"]
    assert "test_download_clients" in known["fix"]
    assert "fix" not in unknown


def test_every_health_fix_is_bilingual() -> None:
    from arr_doctor.i18n import MESSAGES

    fixes = [k for k in MESSAGES if k.startswith("health_")]
    assert len(fixes) >= 20
    assert all(set(MESSAGES[k]) == {"en", "es"} for k in fixes)


async def test_bulk_edit_reports_the_state_read_back(api, call) -> None:
    """After applying, the answer shows what Sonarr stored, not the pre-change state."""
    series = load("sonarr_series_list")
    series[2]["tags"] = [1]
    after = [dict(x) for x in series]
    after[2] = {**after[2], "tags": []}
    api.get(f"{S}/series").mock(side_effect=[httpx.Response(200, json=series), httpx.Response(200, json=series),
                                             httpx.Response(200, json=after)])
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    api.get(f"{S}/tag").respond(json=load("sonarr_tags"))
    api.put(f"{S}/series/editor").respond(json={})
    token = (await call.ok("bulk_edit_apply", service="sonarr", tag="anime", remove_tags=["anime"]))["confirmation_token"]
    out = await call.ok("bulk_edit_apply", service="sonarr", tag="anime", remove_tags=["anime"],
                        confirmation_token=token)
    assert out["matched"] == 1
    assert "tags" not in out["items"]["items"][0]  # the tag is gone in what Sonarr returns now


async def test_preview_rename_explains_renaming_is_off(api, call) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/rename").respond(json=[])
    api.get(f"{S}/config/naming").respond(json={"renameEpisodes": False})
    out = await call.ok("preview_rename", series="The Capture")
    assert out["total"] == 0 and "renameEpisodes" in out["note"]
    out = await call.ok("rename_files", series="The Capture")
    assert out["renamed"] == 0 and "desactivado" in out["message"]


async def test_bulk_edit_several_items_need_the_preview_token(api, call) -> None:
    """Real case: the model applied a change straight away, skipping the preview."""
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    out = await call.ok("bulk_edit_apply", service="sonarr", items=["The Capture", "24"], set_monitored=False)
    assert out["applied"] is False and "confirmation_token" in out["note"] and not put.called
    bad = await call.ok("bulk_edit_apply", service="sonarr", items=["The Capture", "24"], set_monitored=False,
                        confirmation_token="wrong")
    assert bad["applied"] is False and not put.called
    # A token from a preview of different changes does not work either.
    other = await call.ok("bulk_edit_preview", service="sonarr", items=["The Capture", "24"], set_monitored=True)
    stale = await call.ok("bulk_edit_apply", service="sonarr", items=["The Capture", "24"], set_monitored=False,
                          confirmation_token=other["confirmation_token"])
    assert stale["applied"] is False and not put.called


async def test_bulk_edit_single_named_item_applies_directly(api, call) -> None:
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    out = await call.ok("bulk_edit_apply", service="sonarr", items=["The Capture"], set_monitored=False)
    assert out["applied"] is True and put.called


async def test_rename_several_files_needs_the_preview_token(api, call) -> None:
    api.get(f"{S}/config/naming").respond(json={"renameEpisodes": True})
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/rename").respond(json=load("sonarr_rename_s03"))
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    out = await call.ok("rename_files", series="The Capture", season=3)
    assert out["applied"] is False and "preview_rename" in out["note"] and not cmd.called
