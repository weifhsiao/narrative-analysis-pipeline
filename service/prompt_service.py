import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from util.models import CONTEXT_TYPE_PATTERN, PromptTemplate
from util.crud.character_context import get_active_contexts_by_type, list_context_types
from util.crud.prompt import (
    create_prompt_version,
    get_latest_prompt_template,
    get_latest_prompt_templates,
)
from service.character_context_service import load_context

# 開閉標籤：<tag>...</tag>（tag 名為 \w，含中文）；.*? 跨行非貪婪
_TAG_RE = re.compile(r"<(\w+)>.*?</\1>", re.DOTALL)

# run 參數名：pipeline 傳進 load_prompt 的 run_params key 必須在這裡，lint 靠它判斷
RUN_PARAM_NAMES = frozenset({"log_content"})

# lint 用：任一開/閉標籤、舊式 {name} 佔位、填空標籤名的字元規則
_ANY_TAG_RE = re.compile(r"</?(\w+)>")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_SLOT_RE = re.compile(CONTEXT_TYPE_PATTERN)

# prompt 檔(prompts/*.txt)的區段標頭:只認獨立成行
_SYSTEM_HEADER_RE = re.compile(r"^# system instruction[ \t]*$", re.MULTILINE)
_PROMPT_HEADER_RE = re.compile(r"^# prompt[ \t]*$", re.MULTILINE)


@dataclass
class _TagScan:
    """引擎怎麼看一段文字裡的標籤——替換、lint、夾檔判斷都讀這一份,不各自重算。"""

    top: list[re.Match]  # 引擎會逐段處理的最外層 <T>...</T>(由左而右、不重疊)
    nested: dict[str, str]  # 包在某個最外層段落裡、自成一對的填空標籤 → 外層標籤名
    stray: set[str]  # 落在所有最外層段落外、沒配成對的填空標籤名
    swallowed: set[str]  # 會被填、但開閉之間原本有文字(會被整段換掉)的填空標籤名

    @property
    def filled_names(self) -> set[str]:
        """最外層、名稱合規的標籤:引擎實際會去找內容填的那些。"""
        return {m.group(1) for m in self.top if _SLOT_RE.fullmatch(m.group(1))}


def _inner(m: re.Match) -> str:
    """_TAG_RE 比對到的 <T>...</T> 去掉開閉標籤後的內文。"""
    n = len(m.group(1))
    return m.group(0)[n + 2 : -(n + 3)]


def _paired_slots(text: str):
    """text 裡(任意深度)自成一對的填空標籤名。"""
    for m in _TAG_RE.finditer(text):
        if _SLOT_RE.fullmatch(m.group(1)):
            yield m.group(1)
        yield from _paired_slots(_inner(m))


def _scan_tags(text: str) -> _TagScan:
    """用 _TAG_RE 決定引擎會處理哪些標籤:由左而右找「開標籤…最近的同名閉標籤」,
    找到就整段處理、不往內看。所以順序錯的開閉配不起來,
    結構標籤內文順帶提到的標籤名也不影響外面。這是唯一的判定來源。"""
    top = list(_TAG_RE.finditer(text))
    nested: dict[str, str] = {}
    for m in top:
        for t in _paired_slots(_inner(m)):
            nested.setdefault(t, m.group(1))
    spans = [(m.start(), m.end()) for m in top]
    stray = {
        m.group(1)
        for m in _ANY_TAG_RE.finditer(text)
        if _SLOT_RE.fullmatch(m.group(1))
        and not any(a <= m.start() < b for a, b in spans)
    }
    # 引擎從第一個 <T> 配到最近的 </T> 整段換掉:中間若有文字(例:內文先提到 <T> 才是真的填空點),
    # 那段文字送出時會消失
    swallowed = {
        m.group(1) for m in top if _SLOT_RE.fullmatch(m.group(1)) and _inner(m).strip()
    }
    return _TagScan(top=top, nested=nested, stray=stray, swallowed=swallowed)


def _render(
    text: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
    context_types: set[str],
) -> tuple[str, str]:
    """把 text 裡認得的 <T>...</T> 內容換掉,回傳 (快照, 實際送出)。不認得的標籤原樣保留。

    來源判斷：run 參數優先、其次 DB 的 context type；兩者皆非則不動
    （例如 recap 的 <格式>/<參考範例> 這類純結構標籤）。
    快照只填 context、run 參數標籤保持模板原樣(log 由 run range 重建,不重複存);
    實際送出兩者都填。兩份都從同一份原文替換,填進去的內容不會被重掃。
    """
    contexts: dict[str, str] = {}

    def make_repl(fill_run_params: bool):
        def repl(m: re.Match) -> str:
            name = m.group(1)
            if name in run_params:
                if not fill_run_params:
                    return m.group(0)
                content = run_params[name]
            elif name in context_types:
                if name not in contexts:
                    contexts[name] = load_context(db, character_id, name)
                content = contexts[name]
            else:
                return m.group(0)
            # 閉標籤對齊開標籤的縮排（開標籤前有其他文字就不縮）；內容原樣不縮排
            line_start = text.rfind("\n", 0, m.start()) + 1
            indent = text[line_start : m.start()]
            if indent.strip():
                indent = ""
            return f"<{name}>\n{content}\n{indent}</{name}>"

        return repl

    top = _scan_tags(text).top

    def build(repl) -> str:
        out, pos = [], 0
        for m in top:
            out += [text[pos : m.start()], repl(m)]
            pos = m.end()
        return "".join(out) + text[pos:]

    return build(make_repl(False)), build(make_repl(True))


def _fill_tags(
    text: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
    context_types: set[str],
) -> str:
    """實際送出版:run 參數與 context 都填入。"""
    return _render(text, db, character_id, run_params, context_types)[1]


class PromptNotFoundError(LookupError):
    """DB 沒有這支 prompt(還沒從 prompts/*.txt import)。"""


@dataclass
class RenderedPrompt:
    prompt_id: int  # 用到的那一版
    system: str  # 實際送出
    prompt: str
    system_snapshot: str  # 存 DB:context 已填、run 參數標籤留原樣
    prompt_snapshot: str
    used_run_params: frozenset[str]  # 模板裡出現的 run 參數標籤(決定要不要夾 log 檔)


def load_prompt(
    name: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
) -> RenderedPrompt:
    """取 DB 裡該 prompt 的最新版,掃標籤填入內容。

    填空點一律是既有的 <tag></tag>：run 參數（如 log_content）由 run_params 填、
    context 類（relationship/scenario/timeline…）依標籤名到 DB 撈。取代 str.format，
    避免 prompt 內非佔位用途的大括號誤觸發、也讓「要哪些 context」由 prompt 自己宣告。
    """
    template = get_latest_prompt_template(db, name)
    if template is None:
        raise PromptNotFoundError(f"DB 沒有 prompt「{name}」,請先 python -m scripts.import_prompts")

    system = template.system_instruction or ""
    prompt = template.prompt or ""
    context_types = list_context_types(db)
    system_snapshot, system_sent = _render(system, db, character_id, run_params, context_types)
    prompt_snapshot, prompt_sent = _render(prompt, db, character_id, run_params, context_types)
    # 分段看,跟 _render 各段各自填的方式一致;只算引擎真的會處理的最外層標籤
    tags = {m.group(1) for text in (system, prompt) for m in _scan_tags(text).top}

    return RenderedPrompt(
        prompt_id=template.prompt_id,
        system=system_sent,
        prompt=prompt_sent,
        system_snapshot=system_snapshot,
        prompt_snapshot=prompt_snapshot,
        used_run_params=frozenset(tags & run_params.keys()),
    )


def parse_prompt_file(text: str) -> tuple[str, str]:
    """prompts/*.txt → (system, prompt)。

    以獨立成行的 `# prompt` 分段:之前是 system(去掉 `# system instruction` 標頭行)、
    之後是 prompt;沒有 `# prompt` 行就整份當 prompt(標頭行一律不送出)。標頭只認整行,
    內文出現 `# prompts` 之類的字串不會被誤切。
    """
    text = text.lstrip("\ufeff")  # BOM 會讓第一行標頭比不到
    parts = _PROMPT_HEADER_RE.split(text, maxsplit=1)
    if len(parts) == 1:
        return "", _SYSTEM_HEADER_RE.sub("", text, count=1).strip()
    head, body = parts
    return _SYSTEM_HEADER_RE.sub("", head, count=1).strip(), body.strip()


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


def _lint_text(
    db: Session,
    name: str,
    text: str,
    context_types: set[str],
    character_id: int | None,
) -> tuple[list[LintIssue], set[str]]:
    """單支 prompt 的標籤檢查;回傳 (issues, 用到的 context_type)。"""
    issues: list[LintIssue] = []
    used_types: set[str] = set()

    # 判定一律來自 _scan_tags(與引擎替換同一份):段落內只被「提到」而沒配對的名稱視為內文
    scan = _scan_tags(text)
    filled, nested, stray, swallowed = scan.filled_names, scan.nested, scan.stray, scan.swallowed

    for tag in sorted(filled | nested.keys() | stray):
        if tag in nested:
            issues.append(LintIssue(
                "ERROR", name,
                f"<{tag}> 包在 <{nested[tag]}> 裡面,引擎不會填(填空標籤要放在其他標籤外;"
                f"範圍從第一個 <{nested[tag]}> 算起,內文提到這個標籤名也算)",
            ))
            continue
        if tag not in filled:
            issues.append(LintIssue(
                "ERROR", name,
                f"<{tag}> 開閉不成對或閉標籤在開標籤之前,引擎不會填",
            ))
            continue
        if tag in swallowed:
            issues.append(LintIssue(
                "ERROR", name,
                f"<{tag}> 開閉之間有文字,會被整段換掉(範圍從第一個 <{tag}> 算起,內文提到也算)",
            ))
            continue
        if tag in stray:
            issues.append(LintIssue(
                "ERROR", name,
                f"<{tag}> 之外另有未配對的 <{tag}>,會原樣送出",
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

    for ph in sorted(set(_PLACEHOLDER_RE.findall(text)) & (RUN_PARAM_NAMES | context_types)):
        issues.append(LintIssue("WARN", name, f"殘留舊佔位 {{{ph}}},新引擎不會填入"))

    return issues, used_types


def _lint_template(
    db: Session,
    name: str,
    system: str,
    prompt: str,
    context_types: set[str],
    character_id: int | None,
) -> tuple[list[LintIssue], set[str]]:
    """system / prompt 分段 lint:引擎各段各自填,標籤跨段(開在 system、閉在 prompt)
    填不到,要報不成對;某段提到的標籤名也不該影響另一段。同一問題兩段都有只報一次。"""
    issues: list[LintIssue] = []
    used_types: set[str] = set()
    for text in (system, prompt):
        found, used = _lint_text(db, name, text, context_types, character_id)
        issues += [i for i in found if i not in issues]
        used_types |= used
    return issues, used_types


def lint_prompts(
    db: Session,
    character_id: int | None = None,
    names: tuple[str, ...] | None = None,
) -> list[LintIssue]:
    """掃 DB 裡各支 prompt 最新版的填空標籤，列出跑 pipeline 之前就能發現的問題。

    填空標籤 = 名字符合 CONTEXT_TYPE_PATTERN 的 <T>;其他(中文)視為結構標籤,略過。
    ERROR:填空標籤開閉不成對,或既不是 run 參數也不是 DB 既有的 context_type(多半打錯字);
          指定 names 時,DB 裡缺某支 prompt。
    WARN :殘留 {name} 舊佔位(新引擎不會填);指定角色時,該角色缺某個會用到的 type(會填空)。
    INFO :DB 有資料、但沒有任何被檢查的 prompt 用到的 context_type。
    """
    context_types = list_context_types(db)
    templates = get_latest_prompt_templates(db)
    issues: list[LintIssue] = []
    used_types: set[str] = set()

    if names is not None:
        found = {t.prompt_name for t in templates}
        for n in names:
            if n not in found:
                issues.append(LintIssue(
                    "ERROR", n, "DB 沒有這支 prompt(先跑 python -m scripts.import_prompts)",
                ))
        templates = [t for t in templates if t.prompt_name in names]

    for t in templates:
        found_issues, used = _lint_template(
            db, t.prompt_name, t.system_instruction or "", t.prompt or "", context_types, character_id
        )
        issues += found_issues
        used_types |= used

    for t in sorted(context_types - used_types):
        issues.append(LintIssue("INFO", None, f"context_type「{t}」DB 有資料,但沒有任何 prompt 用到"))

    return issues


def save_prompt(
    db: Session,
    name: str,
    system: str,
    prompt: str,
    max_length: int | None = None,
    force: bool = False,
) -> tuple[PromptTemplate | None, list[LintIssue]]:
    """存 prompt 的唯一入口:lint 過了才新增一版;內容與最新版相同就不存(回傳 None)。

    lint 有 ERROR 丟 PromptLintError,force=True 時照存(例:fresh DB 還沒有 context,
    type 一定對不上)。WARN 不擋,連同結果一起回傳給呼叫端顯示。
    """
    issues, _ = _lint_template(db, name, system, prompt, list_context_types(db), None)
    errors = [i for i in issues if i.level == "ERROR"]
    if errors and not force:
        raise PromptLintError(errors)

    latest = get_latest_prompt_template(db, name)
    if latest is not None and (
        latest.system_instruction, latest.prompt, latest.max_length
    ) == (system, prompt, max_length):
        return None, issues

    return create_prompt_version(db, name, system, prompt, max_length), issues
