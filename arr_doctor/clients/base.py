"""Shared async HTTP client for the *arr APIs.

Every HTTP or network failure is turned into an :class:`ArrError` with a short,
human readable message. ``ArrError`` subclasses FastMCP's ``ToolError`` so the
message reaches the model as-is, without a traceback.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from arr_doctor.config import ServiceConfig
from arr_doctor.i18n import t

log = logging.getLogger(__name__)

_ERROR_BODY_MAX = 300


class ArrError(ToolError):
    """A readable error coming from an *arr service."""


class ArrClient:
    """Thin async wrapper around one *arr service API."""

    #: Human name used in error messages ("Sonarr", "Radarr"...).
    display_name: str = "Arr"
    #: API prefix, e.g. ``/api/v3``.
    api_prefix: str = "/api/v3"

    def __init__(self, config: ServiceConfig, timeout: float = 15.0) -> None:
        self.config = config
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def env(self) -> str:
        """Prefix of this service's environment variables (SONARR, RADARR...)."""
        return self.name.upper()

    @property
    def base_url(self) -> str:
        return self.config.url

    # ------------------------------------------------------------------ HTTP

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        timeout: float | None = None,
        accept_status: tuple[int, ...] = (),
    ) -> Any:
        url = f"{self.base_url}{self.api_prefix}{path}"
        clean_params = _clean_params(params)
        try:
            async with httpx.AsyncClient(
                timeout=timeout or self.timeout,
                headers={"X-Api-Key": self.config.api_key, "Accept": "application/json"},
                # Never follow redirects: httpx strips "Authorization" on a cross-origin
                # redirect but NOT our X-Api-Key, so a redirect could leak the key to
                # another host; and 301/302 would silently turn a POST into a GET.
                follow_redirects=False,
            ) as client:
                resp = await client.request(method, url, params=clean_params, json=json)
        except httpx.ConnectError as exc:
            raise ArrError(
                t("connect_error", svc=self.display_name, url=self.base_url, detail=_short(exc), env=self.env)
            ) from exc
        except httpx.TimeoutException as exc:
            raise ArrError(
                t("timeout", svc=self.display_name, secs=timeout or self.timeout, method=method, path=path)
            ) from exc
        except httpx.HTTPError as exc:
            raise ArrError(t("network_error", svc=self.display_name, detail=_short(exc))) from exc

        if resp.is_redirect:
            raise ArrError(
                t(
                    "redirected",
                    svc=self.display_name,
                    code=resp.status_code,
                    location=resp.headers.get("location", "?"),
                    env=self.env,
                )
            )
        if resp.status_code >= 400 and resp.status_code not in accept_status:
            raise ArrError(self._http_error_message(resp, method, path))

        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            # Typical when the URL points to a reverse proxy / login page.
            raise ArrError(t("not_json", svc=self.display_name, method=method, path=path, env=self.env)) from exc

    async def get(self, path: str, /, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, /, json: Any = None, **params: Any) -> Any:
        return await self.request("POST", path, params=params, json=json)

    async def put(self, path: str, /, json: Any = None, **params: Any) -> Any:
        return await self.request("PUT", path, params=params, json=json)

    async def delete(self, path: str, /, json: Any = None, **params: Any) -> Any:
        return await self.request("DELETE", path, params=params, json=json)

    # --------------------------------------------------------------- helpers

    def _http_error_message(self, resp: httpx.Response, method: str, path: str) -> str:
        code = resp.status_code
        ctx = {"svc": self.display_name, "env": self.env, "method": method, "path": path, "code": code}
        detail = _error_detail(resp)
        generic_404 = detail.replace(" ", "").lower() in ("", "notfound")
        if code in (401, 403) or (code == 404 and generic_404):
            return t(f"http_{code}", **ctx)
        if 400 <= code < 500:
            return t("http_4xx", detail=detail or t("request_rejected"), **ctx)
        return t("http_5xx", detail=detail or t("no_detail"), **ctx)

    # -------------------------------------------------------------- commands

    async def system_status(self) -> dict[str, Any]:
        return await self.get("/system/status")

    async def health(self) -> list[dict[str, Any]]:
        return await self.get("/health")

    async def naming_config(self) -> dict[str, Any]:
        """Naming settings (renameEpisodes in Sonarr, renameMovies in Radarr)."""
        return await self.get("/config/naming")

    async def media_management(self) -> dict[str, Any]:
        """Media management settings (recycle bin, hardlinks…). Sonarr and Radarr only."""
        return await self.get("/config/mediamanagement")

    async def command(self, name: str, **body: Any) -> dict[str, Any]:
        return await self.post("/command", json={"name": name, **body})

    async def command_status(self, command_id: int) -> dict[str, Any]:
        return await self.get(f"/command/{command_id}")


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    out: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = value
    return out


def _error_detail(resp: httpx.Response) -> str:
    """Extract a short message from an *arr error body."""
    try:
        body = resp.json()
    except ValueError:
        return _truncate(resp.text.strip())
    if isinstance(body, list):  # validation errors
        msgs = [
            f"{e.get('propertyName')}: {e.get('errorMessage')}" if e.get("propertyName") else str(e.get("errorMessage"))
            for e in body
            if isinstance(e, dict)
        ]
        return _truncate("; ".join(m for m in msgs if m))
    if isinstance(body, dict):
        for key in ("message", "errorMessage", "error", "title"):
            if body.get(key):
                return _truncate(str(body[key]))
    return _truncate(str(body))


def _truncate(text: str, n: int = _ERROR_BODY_MAX) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _short(exc: Exception) -> str:
    return _truncate(str(exc) or exc.__class__.__name__, 120)
