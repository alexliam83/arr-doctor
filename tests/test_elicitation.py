"""User confirmation through the MCP client (elicitation), which the model cannot skip.

Real case: with only the preview token, the model previewed and applied a bulk edit in
the same turn without asking the user.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from arr_doctor.server import build_server
from tests.conftest import S, load, make_settings


def _library(api) -> None:
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/qualityprofile").respond(json=load("sonarr_qualityprofile"))
    api.get(f"{S}/tag").respond(json=load("sonarr_tags"))


def _client(answer: str, seen: list[str]) -> Client:
    async def handler(message: str, response_type: Any, params: Any, context: Any) -> Any:
        seen.append(message)
        return {} if answer == "accept" else ElicitResult(action=answer)

    return Client(build_server(make_settings()), elicitation_handler=handler)


async def test_user_accepts_in_the_client_dialog(api) -> None:
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    seen: list[str] = []
    async with _client("accept", seen) as c:
        res = await c.call_tool(
            "bulk_edit_apply", {"service": "sonarr", "items": ["The Capture", "24"], "set_monitored": False}
        )
    assert res.structured_content["applied"] is True and put.called  # no token needed: the user said yes
    assert "2" in seen[0] and "The Capture" in seen[0]


async def test_user_declines_in_the_client_dialog(api) -> None:
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    seen: list[str] = []
    async with _client("decline", seen) as c:
        # Even with a valid token from a preview, the user's "no" wins.
        args = {"service": "sonarr", "items": ["The Capture", "24"], "set_monitored": False}
        token = (await c.call_tool("bulk_edit_preview", args)).structured_content["confirmation_token"]
        res = await c.call_tool("bulk_edit_apply", {**args, "confirmation_token": token})
    assert res.structured_content["applied"] is False and not put.called
    assert "no lo reintentes" in res.structured_content["message"]


async def test_single_named_item_does_not_ask(api) -> None:
    _library(api)
    put = api.put(f"{S}/series/editor").respond(json={})
    seen: list[str] = []
    async with _client("decline", seen) as c:
        await c.call_tool("bulk_edit_apply", {"service": "sonarr", "items": ["The Capture"], "set_monitored": False})
    assert put.called and seen == []


async def test_rename_several_files_asks_the_user(api) -> None:
    api.get(f"{S}/config/naming").respond(json={"renameEpisodes": True})
    api.get(f"{S}/series").respond(json=load("sonarr_series_list"))
    api.get(f"{S}/rename").respond(json=load("sonarr_rename_s03"))
    cmd = api.post(f"{S}/command").respond(json=load("sonarr_command_queued"))
    seen: list[str] = []
    async with _client("decline", seen) as c:
        res = await c.call_tool("rename_files", {"series": "The Capture", "season": 3})
    assert res.structured_content["applied"] is False and not cmd.called and "2" in seen[0]
