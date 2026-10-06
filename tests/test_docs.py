from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("lang", ["en", "es"])
async def test_tools_doc_is_up_to_date(lang: str) -> None:
    spec = importlib.util.spec_from_file_location("gen_tools_doc", ROOT / "scripts" / "gen_tools_doc.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected = await mod.build(lang)
    current = (ROOT / "docs" / mod.OUTPUTS[lang]).read_text(encoding="utf-8")
    assert current == expected, "docs/TOOLS*.md are stale: run python scripts/gen_tools_doc.py"
