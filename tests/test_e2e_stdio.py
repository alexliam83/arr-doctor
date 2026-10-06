"""End-to-end: launch the real server process over stdio against a fake Sonarr.

No mocks inside the process: this exercises the console script / ``python -m``
entry points, stdio framing, logging to stderr and real HTTP, on every OS the CI
runs (Linux and Windows).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import sysconfig
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from tests.conftest import load

API_KEY = "e2e-key"


class FakeSonarr(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.headers.get("X-Api-Key") != API_KEY:
            self._send(401, {})
            return
        route = self.path.split("?")[0]
        if route == "/api/v3/system/status":
            self._send(200, load("sonarr_system_status"))
        elif route == "/api/v3/queue":
            self._send(200, load("sonarr_queue"))
        else:
            self._send(404, {"message": "NotFound"})

    def _send(self, code: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass


@pytest.fixture
def fake_sonarr() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSonarr)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _console_script() -> str | None:
    # In a venv the scripts sit next to python(.exe); in a system install they go to
    # sysconfig's "scripts" dir (e.g. <prefix>\\Scripts on Windows).
    dirs = {str(Path(sys.executable).parent), sysconfig.get_path("scripts")}
    return shutil.which("arr-doctor", path=os.pathsep.join(dirs))


def _launchers() -> list[tuple[str, list[str]]]:
    out = [(sys.executable, ["-m", "arr_doctor.server"])]
    script = _console_script()
    if script:
        out.append((script, []))
    return out


def _env(url: str, key: str, lang: str = "en") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SONARR_", "RADARR_", "PROWLARR_", "ARR_"))}
    # The server also reads the repository's .env. Explicit empty values win over it,
    # so a developer's real Radarr/Prowlarr are never contacted by this test.
    env.update(
        SONARR_URL=url, SONARR_API_KEY=key, ARR_LANG=lang, PYTHONIOENCODING="",
        RADARR_URL="", RADARR_API_KEY="", PROWLARR_URL="", PROWLARR_API_KEY="", ARR_DOWNLOADS_PATH="",
    )
    return env


@pytest.mark.parametrize("launcher", _launchers(), ids=lambda launcher: Path(launcher[0]).name)
async def test_stdio_server_end_to_end(fake_sonarr: str, launcher: tuple[str, list[str]], tmp_path: Path) -> None:
    command, args = launcher
    transport = StdioTransport(command, args, env=_env(fake_sonarr, API_KEY), cwd=str(tmp_path))
    async with Client(transport) as client:
        names = {t.name for t in await client.list_tools()}
        assert {"get_system_status", "get_queue", "manual_import"} <= names
        assert "get_movie" not in names  # Radarr not configured -> not registered

        status = await client.call_tool("get_system_status", {})
        sonarr = status.structured_content["services"][0]
        assert sonarr["ok"] is True and sonarr["version"].startswith("4.")

        queue = await client.call_tool("get_queue", {"service": "sonarr", "only_problems": True})
        assert {i["id"] for i in queue.structured_content["sonarr"]["items"]} == {12, 13}


async def test_stdio_errors_keep_non_ascii_text(fake_sonarr: str, tmp_path: Path) -> None:
    """Spanish messages (accents) must survive stdio on every platform/console encoding."""
    transport = StdioTransport(
        sys.executable, ["-m", "arr_doctor.server"], env=_env(fake_sonarr, "wrong", lang="es"), cwd=str(tmp_path)
    )
    async with Client(transport) as client:
        res = await client.call_tool("get_queue", {"service": "sonarr"}, raise_on_error=False)
    assert res.is_error
    assert res.content[0].text == "Sonarr devolvió 401: API key incorrecta (revisa SONARR_API_KEY)."


def test_console_script_is_installed() -> None:
    assert _console_script(), "arr-doctor entry point not found next to the Python interpreter"
