"""契約測試：真正的 prompts/*.txt 經 import 進 DB 後，要能被 pipeline 正確使用。

改 prompt 文字時最容易出事的是標籤打錯、殘留舊佔位，這裡在跑 AI 之前就擋下。
走的是正式的存 prompt 路徑（parse_prompt_file → save_prompt），等同 scripts.import_prompts。
"""
import re
from pathlib import Path

import pytest

from service.pipeline_service import PIPELINE_PROMPTS
from service.prompt_service import (
    RUN_PARAM_NAMES,
    lint_prompts,
    load_prompt,
    parse_prompt_file,
    save_prompt,
)
from tests.helpers import add_character, add_context

REAL_PROMPTS = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = sorted(REAL_PROMPTS.glob("*.txt"))

# pipeline prompt 目前用到的 context type；新增 type 時這裡也要補
CONTEXT_TYPES = ("relationship", "scenario", "timeline")


@pytest.fixture
def character(db):
    cid = add_character(db)
    for t in CONTEXT_TYPES:
        add_context(db, cid, t, f"<<{t}_CONTENT>>")
    return cid


@pytest.fixture
def imported(db, character):
    for path in PROMPT_FILES:
        save_prompt(db, path.stem, *parse_prompt_file(path.read_text(encoding="utf-8")))
    return character


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.stem)
def test_real_prompt_saves_without_errors_or_warnings(db, character, path):
    template, issues = save_prompt(
        db, path.stem, *parse_prompt_file(path.read_text(encoding="utf-8"))
    )

    assert template is not None
    assert [i for i in issues if i.level in ("ERROR", "WARN")] == []


def test_pipeline_prompts_have_no_lint_errors_or_warnings(db, imported):
    issues = [
        i
        for i in lint_prompts(db, imported, PIPELINE_PROMPTS)
        if i.level in ("ERROR", "WARN")
    ]

    assert issues == []


@pytest.mark.parametrize("name", PIPELINE_PROMPTS)
def test_every_slot_in_pipeline_prompt_gets_filled(db, imported, name):
    r = load_prompt(name, db, imported, {"log_content": "<<LOG>>"})
    rendered = f"{r.system}\n{r.prompt}"

    slots = set(re.findall(r"<([a-z0-9_]+)>", rendered))
    assert slots, f"{name} 沒有任何填空標籤"
    for slot in slots:
        expected = "<<LOG>>" if slot in RUN_PARAM_NAMES else f"<<{slot}_CONTENT>>"
        assert re.search(rf"<{slot}>\n{re.escape(expected)}\n\s*</{slot}>", rendered), (
            f"{name} 的 <{slot}> 沒有被填入"
        )
