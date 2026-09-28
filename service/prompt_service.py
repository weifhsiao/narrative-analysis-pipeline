import re

from sqlalchemy.orm import Session

from util.file_util import BASE_DIR
from util.crud.character_context import list_context_types
from service.character_context_service import load_context

# 開閉標籤：<tag>...</tag>（tag 名為 \w，含中文）；.*? 跨行非貪婪
_TAG_RE = re.compile(r"<(\w+)>.*?</\1>", re.DOTALL)


def _fill_tags(
    text: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
    context_types: set[str],
) -> str:
    """把 text 裡認得的 <T>...</T> 內容換掉；不認得的標籤原樣保留。

    來源判斷：run 參數優先、其次 DB 的 context type；兩者皆非則不動
    （例如 recap 的 <格式>/<參考範例> 這類純結構標籤）。
    """

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name in run_params:
            content = run_params[name]
        elif name in context_types:
            content = load_context(db, character_id, name)
        else:
            return m.group(0)
        return f"<{name}>\n{content}\n</{name}>"

    return _TAG_RE.sub(repl, text)


def load_prompt(
    name: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
) -> tuple[str, str]:
    """讀 prompt 檔，切出 (system, prompt) 後掃標籤填入內容。

    填空點一律是既有的 <tag></tag>：run 參數（如 log_content）由 run_params 填、
    context 類（relationship/scenario/timeline…）依標籤名到 DB 撈。取代 str.format，
    避免 prompt 內非佔位用途的大括號誤觸發、也讓「要哪些 context」由 prompt 自己宣告。
    """
    prompt_template = (BASE_DIR / "prompts" / f"{name}.txt").read_text(encoding="utf-8")

    system = ""
    prompt = prompt_template

    if "# system instruction" in prompt_template and "# prompt" in prompt_template:
        parts = prompt_template.split("# prompt", 1)
        system = parts[0].replace("# system instruction", "").strip()
        prompt = parts[1].strip()

    context_types = list_context_types(db)
    system = _fill_tags(system, db, character_id, run_params, context_types)
    prompt = _fill_tags(prompt, db, character_id, run_params, context_types)

    return system, prompt
