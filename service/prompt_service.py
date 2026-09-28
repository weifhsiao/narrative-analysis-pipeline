import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from util.file_util import BASE_DIR
from util.models import CONTEXT_TYPE_PATTERN
from util.crud.character_context import get_active_contexts_by_type, list_context_types
from service.character_context_service import load_context

# 開閉標籤：<tag>...</tag>（tag 名為 \w，含中文）；.*? 跨行非貪婪
_TAG_RE = re.compile(r"<(\w+)>.*?</\1>", re.DOTALL)

# run 參數名：pipeline 傳進 load_prompt 的 run_params key 必須在這裡，lint 靠它判斷
RUN_PARAM_NAMES = frozenset({"log_content"})

# lint 用：開/閉標籤分開抓（才抓得到不成對）、舊式 {name} 佔位、填空標籤名的字元規則
_OPEN_RE = re.compile(r"<(\w+)>")
_CLOSE_RE = re.compile(r"</(\w+)>")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_SLOT_RE = re.compile(CONTEXT_TYPE_PATTERN)


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
        # 閉標籤對齊開標籤的縮排（開標籤前有其他文字就不縮）；內容原樣不縮排
        line_start = text.rfind("\n", 0, m.start()) + 1
        indent = text[line_start : m.start()]
        if indent.strip():
            indent = ""
        return f"<{name}>\n{content}\n{indent}</{name}>"

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


@dataclass
class LintIssue:
    level: str  # ERROR / WARN / INFO
    prompt: str | None  # prompt 檔名(不含 .txt);全域性問題為 None
    message: str


class PromptLintError(Exception):
    """pipeline 開跑前 lint 有 ERROR:標籤對不上,送出去的 prompt 會缺內容,直接中止。"""

    def __init__(self, issues: list[LintIssue]):
        self.issues = issues
        super().__init__("; ".join(f"{i.prompt}: {i.message}" for i in issues))


def lint_prompts(db: Session, character_id: int | None = None) -> list[LintIssue]:
    """掃 prompts/*.txt 的填空標籤，列出跑 pipeline 之前就能發現的問題。

    填空標籤 = 名字符合 CONTEXT_TYPE_PATTERN 的 <T>;其他(中文)視為結構標籤,略過。
    ERROR:填空標籤開閉不成對,或既不是 run 參數也不是 DB 既有的 context_type(多半打錯字)。
    WARN :殘留 {name} 舊佔位(新引擎不會填);指定角色時,該角色缺某個會用到的 type(會填空)。
    INFO :DB 有資料、但沒有任何 prompt 用到的 context_type。
    """
    context_types = list_context_types(db)
    known = RUN_PARAM_NAMES | context_types
    issues: list[LintIssue] = []
    used_types: set[str] = set()

    for path in sorted((BASE_DIR / "prompts").glob("*.txt")):
        name = path.stem
        text = path.read_text(encoding="utf-8")

        opens = Counter(t for t in _OPEN_RE.findall(text) if _SLOT_RE.fullmatch(t))
        closes = Counter(t for t in _CLOSE_RE.findall(text) if _SLOT_RE.fullmatch(t))

        for tag in sorted(opens.keys() | closes.keys()):
            if opens[tag] != closes[tag]:
                issues.append(LintIssue(
                    "ERROR", name,
                    f"<{tag}> 開閉不成對(開 {opens[tag]}、閉 {closes[tag]}),引擎不會填",
                ))
                continue
            if tag in RUN_PARAM_NAMES:
                continue
            if tag not in context_types:
                issues.append(LintIssue(
                    "ERROR", name,
                    f"<{tag}> 不是 run 參數,也不是 DB 既有的 context_type(打錯字或 type 不存在)",
                ))
                continue
            used_types.add(tag)
            if character_id is not None and not get_active_contexts_by_type(db, character_id, tag):
                issues.append(LintIssue(
                    "WARN", name,
                    f"角色 {character_id} 沒有 active 的 {tag},跑的時候 <{tag}> 會填空",
                ))

        for ph in sorted(set(_PLACEHOLDER_RE.findall(text)) & known):
            issues.append(LintIssue("WARN", name, f"殘留舊佔位 {{{ph}}},新引擎不會填入"))

    for t in sorted(context_types - used_types):
        issues.append(LintIssue("INFO", None, f"context_type「{t}」DB 有資料,但沒有任何 prompt 用到"))

    return issues
