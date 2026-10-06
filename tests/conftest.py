from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import respx
from fastmcp import Client

from arr_doctor.config import Settings
from arr_doctor.i18n import set_language
from arr_doctor.server import build_server

FIXTURES = Path(__file__).parent / "fixtures"

SONARR = "http://sonarr.test:8989"
RADARR = "http://radarr.test:7878"
PROWLARR = "http://prowlarr.test:9696"
S = f"{SONARR}/api/v3"
R = f"{RADARR}/api/v3"
P = f"{PROWLARR}/api/v1"


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "sonarr_url": SONARR,
        "sonarr_api_key": "sonarr-key",
        "radarr_url": RADARR,
        "radarr_api_key": "radarr-key",
        "prowlarr_url": PROWLARR,
        "prowlarr_api_key": "prowlarr-key",
        "arr_timeout": 5,
        # Most assertions check the Spanish messages; test_i18n covers English.
        "arr_lang": "es",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def _spanish_messages():
    set_language("es")
    yield
    set_language("en")


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SONARR_URL", "SONARR_API_KEY", "RADARR_URL", "RADARR_API_KEY",
        "PROWLARR_URL", "PROWLARR_API_KEY", "ARR_READONLY", "ARR_TIMEOUT", "ARR_DOWNLOADS_PATH", "ARR_LANG",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
async def mcp_client(settings: Settings):
    async with Client(build_server(settings)) as client:
        yield client


class Caller:
    def __init__(self, client: Client) -> None:
        self.client = client

    async def ok(self, tool: str, **args: Any) -> Any:
        res = await self.client.call_tool(tool, args, raise_on_error=False)
        assert not res.is_error, res.content[0].text if res.content else res
        return res.structured_content

    async def error(self, tool: str, **args: Any) -> str:
        res = await self.client.call_tool(tool, args, raise_on_error=False)
        assert res.is_error, f"expected error, got {res.structured_content}"
        return res.content[0].text


@pytest.fixture
def call(mcp_client: Client) -> Caller:
    return Caller(mcp_client)
