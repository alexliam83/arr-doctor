from __future__ import annotations

import httpx
import pytest
from fastmcp import Client

from arr_doctor.server import build_server, main
from tests.conftest import P, R, S, load, make_settings

WRITE_TOOLS = {
    "search_episodes", "search_season", "search_missing", "search_movie", "set_monitored",
    "remove_from_queue", "refresh_item", "add_series", "add_movie", "manual_import",
    "set_indexer_enabled", "test_indexers", "grab_release", "bulk_edit_apply", "rename_files",
}
SONARR_ONLY = {"get_series", "get_episodes", "search_episodes", "search_season", "add_series"}
RADARR_ONLY = {"get_movie", "search_movie", "add_movie"}
PROWLARR = {"list_indexers", "get_indexer_stats", "set_indexer_enabled", "test_indexers"}


async def tool_names(**overrides) -> set[str]:
    return set(await build_server(make_settings(**overrides)).get_tools())


async def test_all_services_register_everything() -> None:
    names = await tool_names()
    assert names >= WRITE_TOOLS | SONARR_ONLY | RADARR_ONLY | PROWLARR
    assert "get_system_status" in names


async def test_readonly_registers_no_write_tools() -> None:
    names = await tool_names(arr_readonly=True)
    assert not names & WRITE_TOOLS
    assert {"get_queue", "list_indexers", "find_orphan_downloads"} <= names
    assert "bulk_edit_preview" in names and "preview_rename" in names  # previews are read-only


async def test_unconfigured_services_are_not_registered() -> None:
    names = await tool_names(radarr_url=None, prowlarr_api_key=None)
    assert not names & RADARR_ONLY
    assert not names & PROWLARR
    assert names >= SONARR_ONLY


async def test_annotations() -> None:
    tools = {t.name: t for t in (await build_server(make_settings()).get_tools()).values()}
    assert tools["get_queue"].annotations.readOnlyHint is True
    assert tools["remove_from_queue"].annotations.destructiveHint is True
    assert tools["manual_import"].annotations.destructiveHint is True
    assert tools["search_episodes"].annotations.readOnlyHint is False


async def test_descriptions_are_english_with_examples() -> None:
    tools = (await build_server(make_settings()).get_tools()).values()
    for tool in tools:
        assert tool.description, tool.name
        assert "Example" in tool.description or tool.name == "get_system_status" or "Examples" in tool.description


async def test_system_status(api, call) -> None:
    api.get(f"{S}/system/status").respond(json=load("sonarr_system_status"))
    api.get(f"{R}/system/status").respond(json=load("radarr_system_status"))
    api.get(f"{P}/system/status").mock(side_effect=httpx.ConnectError("refused"))
    out = await call.ok("get_system_status")
    by = {s["service"]: s for s in out["services"]}
    assert by["sonarr"]["ok"] and by["sonarr"]["version"].startswith("4.")
    assert by["radarr"]["version"].startswith("6.2")
    assert by["prowlarr"]["ok"] is False
    assert "puerto" in by["prowlarr"]["error"]


async def test_system_status_bad_key(api, call) -> None:
    api.get(f"{S}/system/status").respond(401)
    api.get(f"{R}/system/status").respond(json=load("radarr_system_status"))
    api.get(f"{P}/system/status").respond(json=load("prowlarr_system_status"))
    out = await call.ok("get_system_status")
    assert "API key incorrecta" in out["services"][0]["error"]


def test_main_exits_without_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("arr_doctor.config._ENV_FILES", ())
    monkeypatch.setattr("arr_doctor.server.Settings", lambda: make_settings(sonarr_url=None, radarr_url=None))
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


async def test_in_memory_client_lists_tools() -> None:
    async with Client(build_server(make_settings())) as c:
        tools = await c.list_tools()
    assert len(tools) >= 30
