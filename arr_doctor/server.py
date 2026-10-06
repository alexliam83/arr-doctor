"""FastMCP server: builds the tool set from the configured services and runs over stdio.

Nothing but the MCP protocol may be written to stdout. Logging goes to stderr.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import warnings
from typing import Any

from fastmcp import FastMCP

from arr_doctor import __version__
from arr_doctor.clients import ArrClient, ArrError
from arr_doctor.config import Settings
from arr_doctor.i18n import set_language, t
from arr_doctor.tools import actions, diagnostics, indexers, library, maintenance, troubleshoot
from arr_doctor.tools.common import READ_ONLY, Services

log = logging.getLogger("arr_doctor")

INSTRUCTIONS = """\
Tools for a home media stack: Sonarr (TV series), Radarr (movies) and optionally
Prowlarr (indexers). Series and movies can be referenced by ID or by title; when a
title is ambiguous the tool returns the candidates instead of guessing. Lists are
capped by `limit` and flagged with `truncated`. Searches and imports are
asynchronous commands: use get_command_status with the returned command_id to
follow them (do not poll in a tight loop).

Good practice (enforced by the tools):
- Sonarr/Radarr find new releases through RSS by themselves. Only search when the user
  asks for something specific; never search the whole library "just in case".
- Searches, grabs and indexer tests count against an hourly indexer budget, to respect
  indexer API/grab limits. Items searched in the last hour are skipped unless forced.
- Mass searches, mass queue removals, bulk edits and renames return a preview or a
  count first: show it to the user and only repeat with confirm/apply when they agree.
- Before any destructive action, tell the user exactly what will change.
"""


def build_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings()
    set_language(settings.arr_lang)
    svc = Services.from_settings(settings)
    mcp = FastMCP("arr-doctor", instructions=INSTRUCTIONS, version=__version__)

    @mcp.tool(annotations=READ_ONLY)
    async def get_system_status() -> dict[str, Any]:
        """Version and reachability of every configured service (Sonarr, Radarr, Prowlarr).

        Use it first when something fails, to check connectivity and API keys.
        Examples: "Are Sonarr and Radarr up?", "Which Radarr version am I running?"
        """
        clients: list[ArrClient] = [c for c in (svc.sonarr, svc.radarr, svc.prowlarr) if c]

        async def one(client: ArrClient) -> dict[str, Any]:
            try:
                st = await client.system_status()
            except ArrError as exc:
                return {"service": client.name, "url": client.base_url, "ok": False, "error": str(exc)}
            return {
                "service": client.name,
                "url": client.base_url,
                "ok": True,
                "app": st.get("appName"),
                "version": st.get("version"),
                "branch": st.get("branch"),
                "docker": st.get("isDocker"),
                "start_time": st.get("startTime"),
            }

        results = await asyncio.gather(*(one(c) for c in clients))
        return {
            "readonly_mode": settings.arr_readonly,
            "downloads_path": settings.arr_downloads_path,
            "services": list(results),
        }

    if svc.has_arr:
        library.register(mcp, svc)
        diagnostics.register(mcp, svc)
        troubleshoot.register(mcp, svc, readonly=settings.arr_readonly)
        maintenance.register(mcp, svc, readonly=settings.arr_readonly)
        if not settings.arr_readonly:
            actions.register(mcp, svc)
    if svc.prowlarr:
        indexers.register(mcp, svc, readonly=settings.arr_readonly)

    return mcp


class _DropExpectedToolErrors(logging.Filter):
    """fastmcp logs every tool exception with a full traceback. ArrError is an
    expected, already readable error, so keep stderr quiet for those."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, ArrError)


def _configure_logging() -> None:
    # Windows pipes default to the ANSI code page (e.g. cp1252). Logs may contain
    # any Unicode (titles, paths, Spanish messages): never let encoding break them.
    if hasattr(sys.stderr, "reconfigure"):
        if sys.stderr.isatty():
            sys.stderr.reconfigure(errors="backslashreplace")
        else:
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request at INFO; keep stderr readable.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for name in ("fastmcp.fastmcp.tools.tool_manager", "fastmcp.fastmcp.server.server"):
        logging.getLogger(name).addFilter(_DropExpectedToolErrors())
    # Third-party deprecation noise (authlib) is irrelevant for users.
    warnings.filterwarnings("ignore", category=DeprecationWarning)


def main() -> None:
    _configure_logging()
    settings = Settings()
    set_language(settings.arr_lang)

    for name in settings.incomplete_services():
        log.warning(t("incomplete_service", svc=name.capitalize(), env=name.upper()))
    if not (settings.sonarr or settings.radarr):
        log.error(t("no_services"))
        sys.exit(1)

    configured = [n for n in ("sonarr", "radarr", "prowlarr") if getattr(settings, n)]
    log.info(
        "arr-doctor %s: services=%s readonly=%s lang=%s", __version__, ",".join(configured), settings.arr_readonly, settings.arr_lang
    )
    build_server(settings).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
