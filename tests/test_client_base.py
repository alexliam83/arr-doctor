from __future__ import annotations

import httpx
import pytest

from arr_doctor.clients import ArrError, SonarrClient
from arr_doctor.config import ServiceConfig
from tests.conftest import SONARR, S


@pytest.fixture
def sonarr() -> SonarrClient:
    return SonarrClient(ServiceConfig("sonarr", SONARR, "secret"), timeout=2)


async def test_sends_api_key_header(api, sonarr) -> None:
    route = api.get(f"{S}/system/status").respond(json={"version": "4"})
    assert (await sonarr.system_status())["version"] == "4"
    assert route.calls.last.request.headers["X-Api-Key"] == "secret"


async def test_bool_and_list_params(api, sonarr) -> None:
    route = api.get(f"{S}/history").respond(json={"records": []})
    await sonarr.history(10, series_id=3, event_type=1)
    params = route.calls.last.request.url.params
    assert params["includeSeries"] == "true"
    assert params.get_list("seriesIds") == ["3"]
    assert params.get_list("eventType") == ["1"]


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {}, "Sonarr devolvió 401: API key incorrecta"),
        (403, {}, "403"),
        (404, {"message": "NotFound"}, "Sonarr devolvió 404: no existe /series/99"),
        (500, {"message": "database is locked"}, "Sonarr devolvió 500 (error interno) en GET /series/99: database is locked"),
    ],
)
async def test_http_errors_are_readable(api, sonarr, status, body, expected) -> None:
    api.get(f"{S}/series/99").respond(status, json=body)
    with pytest.raises(ArrError) as err:
        await sonarr.get_series(99)
    assert expected in str(err.value)


async def test_validation_errors(api, sonarr) -> None:
    api.post(f"{S}/series").respond(
        400, json=[{"propertyName": "RootFolderPath", "errorMessage": "Invalid Path"}]
    )
    with pytest.raises(ArrError, match="RootFolderPath: Invalid Path"):
        await sonarr.add_series({"title": "x"})


async def test_connect_error_suggests_port_change(api, sonarr) -> None:
    api.get(f"{S}/system/status").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ArrError) as err:
        await sonarr.system_status()
    msg = str(err.value)
    assert "No se pudo conectar con Sonarr" in msg
    assert "puerto" in msg and "Synology" in msg
    assert "SONARR_URL" in msg


async def test_timeout(api, sonarr) -> None:
    api.get(f"{S}/queue").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ArrError, match="no respondió en 2 s"):
        await sonarr.queue()


async def test_non_json_response(api, sonarr) -> None:
    api.get(f"{S}/system/status").respond(200, text="<html>login</html>")
    with pytest.raises(ArrError, match="no es JSON"):
        await sonarr.system_status()


async def test_empty_body_returns_none(api, sonarr) -> None:
    api.delete(f"{S}/queue/5").respond(200)
    assert await sonarr.remove_from_queue(5, True, False, False) is None


async def test_accept_status(api) -> None:
    from arr_doctor.clients import ProwlarrClient

    prowlarr = ProwlarrClient(ServiceConfig("prowlarr", "http://p:1", "k"))
    api.post("http://p:1/api/v1/indexer/testall").respond(400, json=[{"id": 1, "isValid": False}])
    assert await prowlarr.test_all() == [{"id": 1, "isValid": False}]


async def test_404_with_useful_detail_is_shown(api, sonarr) -> None:
    api.post(f"{S}/release").respond(
        404, json={"message": "Couldn't find requested release in cache, try searching again"}
    )
    with pytest.raises(ArrError, match="try searching again"):
        await sonarr.grab_release("guid", 1)


async def test_redirects_are_not_followed(api, sonarr) -> None:
    """A redirect to another host must never receive the API key."""
    api.get(f"{S}/system/status").respond(301, headers={"Location": "http://evil.example/api/v3/system/status"})
    evil = api.get("http://evil.example/api/v3/system/status").respond(json={})
    with pytest.raises(ArrError) as err:
        await sonarr.system_status()
    assert "http://evil.example/api/v3/system/status" in str(err.value) and "SONARR_URL" in str(err.value)
    assert not evil.called


async def test_post_is_never_turned_into_get_by_a_redirect(api, sonarr) -> None:
    api.post(f"{S}/command").respond(302, headers={"Location": f"{S}/somewhere"})
    other = api.get(f"{S}/somewhere").respond(json={})
    with pytest.raises(ArrError, match="302"):
        await sonarr.command("RefreshSeries", seriesIds=[1])
    assert not other.called
