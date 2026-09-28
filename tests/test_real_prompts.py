"""契約測試：真正的 prompts/*.txt 要能被 pipeline 正確使用。

改 prompt 文字時最容易出事的是標籤打錯、殘留舊佔位，這裡在跑 AI 之前就擋下。
prompt 入庫後，這支改成檢查 DB 裡的 prompt（見 vault 的待辦）。
"""
import re
import shutil
from pathlib import Path

import pytest

from service.pipeline_service import PIPELINE_PROMPTS
from service.prompt_service import RUN_PARAM_NAMES, lint_prompts, load_prompt
from tests.helpers import add_character, add_context

REAL_PROMPTS = Path(__file__).parent.parent / "prompts"

# pipeline prompt 目前用到的 context type；新增 type 時這裡也要補
CONTEXT_TYPES = ("relationship", "scenario", "timeline")


@pytest.fixture
def character(db, prompts_dir):
    shutil.copytree(REAL_PROMPTS, prompts_dir, dirs_exist_ok=True)
    cid = add_character(db)
    for t in CONTEXT_TYPES:
        add_context(db, cid, t, f"<<{t}_CONTENT>>")
    return cid


def test_pipeline_prompts_have_no_lint_errors_or_warnings(db, character):
    issues = [
        i
        for i in lint_prompts(db, character)
        if i.prompt in PIPELINE_PROMPTS and i.level in ("ERROR", "WARN")
    ]

    assert issues == []


@pytest.mark.parametrize("name", PIPELINE_PROMPTS)
def test_every_slot_in_pipeline_prompt_gets_filled(db, character, name):
    system, prompt = load_prompt(name, db, character, {"log_content": "<<LOG>>"})
    rendered = f"{system}\n{prompt}"

    slots = set(re.findall(r"<([a-z0-9_]+)>", rendered))
    assert slots, f"{name} 沒有任何填空標籤"
    for slot in slots:
        expected = "<<LOG>>" if slot in RUN_PARAM_NAMES else f"<<{slot}_CONTENT>>"
        assert re.search(rf"<{slot}>\n{re.escape(expected)}\n\s*</{slot}>", rendered), (
            f"{name} 的 <{slot}> 沒有被填入"
        )
