from __future__ import annotations

from fastmcp import Client

from arr_doctor.i18n import MESSAGES, set_language, t
from arr_doctor.server import build_server
from tests.conftest import S, make_settings


def test_every_message_has_both_languages() -> None:
    for key, entry in MESSAGES.items():
        assert set(entry) == {"en", "es"}, key


def test_placeholders_match_between_languages() -> None:
    import string

    fmt = string.Formatter()
    for key, entry in MESSAGES.items():
        fields = [{f for _, f, _, _ in fmt.parse(text) if f} for text in entry.values()]
        assert fields[0] == fields[1], key


def test_language_switch() -> None:
    set_language("en")
    assert t("not_in_queue") == "not in the queue"
    set_language("es-ES")
    assert t("not_in_queue") == "no está en la cola"


def test_settings_lang_normalised() -> None:
    assert make_settings(arr_lang="ES").arr_lang == "es"
    assert make_settings(arr_lang="").arr_lang == "en"


async def test_errors_in_english_by_default(api) -> None:
    api.get(f"{S}/queue").respond(401)
    server = build_server(make_settings(arr_lang="en"))
    async with Client(server) as c:
        res = await c.call_tool("get_queue", {"service": "sonarr"}, raise_on_error=False)
    assert res.content[0].text == "Sonarr returned 401: wrong API key (check SONARR_API_KEY)."
