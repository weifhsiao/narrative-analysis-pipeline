"""context 的遊戲檢索關鍵字建議:把這段內容與同線其他段已用的關鍵字交給 AI,回傳候選詞讓使用者挑。

只建議不寫入:要不要採用、怎麼組合由使用者在 UI 決定,存檔走一般的 PATCH。
prompt 在 prompts/keywords.txt(跟 pipeline 的 prompt 一樣入庫、有版本)。
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import util.ai_client as ai_client
from util import config
from service.prompt_service import load_prompt
from util.ai_client import TokenUsage
from util.crud.character_context import get_context, get_contexts_by_character
from util.crud.novel_log import get_senders

KEYWORD_PROMPT = "keywords"
KEYWORD_SEPARATOR = "、"
KEYWORDS_MAX_CHARS = 30  # 遊戲端欄位上限,含分隔符
CANDIDATE_MAX_CHARS = 12  # 單一候選超過這長度多半是整句,丟掉
MIN_CANDIDATES = 3  # 少於這個數量視為格式沒照做,重試一次

# 讀取時三種分隔都接受(使用者手填可能混用),產生時一律用「、」
_SPLIT_RE = re.compile(r"[、,，|｜\n]")
# 模型輸出的兩行:「具體詞：…」「事件標籤：…」(冒號全半形都認)
_LINE_RE = re.compile(r"^\s*(具體詞|事件標籤)\s*[:：]\s*(.*)$")
TERM, LABEL = "term", "label"


class ContextNotFoundError(LookupError):
    pass


@dataclass
class Candidate:
    text: str
    kind: str  # term = 具體詞,label = 事件標籤
    used_elsewhere: bool  # 同線其他段的關鍵字已經用過這個詞
    mentioned_elsewhere: bool  # 同線其他段的內容也有出現(反覆出現的主題,區別力低)
    has_name: bool  # 含角色名(單獨的角色名當關鍵字分不出是哪一段)


@dataclass
class KeywordSuggestion:
    candidates: list[Candidate]
    usage: TokenUsage
    warnings: list[str] = field(default_factory=list)


def split_keywords(text: str | None) -> list[str]:
    """關鍵字字串 → 清單:三種分隔都認,去空白、去空項、去重(保留順序)。"""
    seen, out = set(), []
    for part in _SPLIT_RE.split(text or ""):
        word = part.strip().strip("「」『』\"'。．.")
        if word and word not in seen:
            seen.add(word)
            out.append(word)
    return out


def parse_candidates(text: str) -> list[tuple[str, str]]:
    """模型輸出 → [(詞, kind)]。照「具體詞：」「事件標籤：」分行;沒有這兩個開頭(格式沒照做)時全部當具體詞。
    同一個詞只留第一次出現。"""
    lines = (text or "").splitlines()
    matched = [m for m in (_LINE_RE.match(line) for line in lines) if m]
    if matched:  # 有分行格式時只收那兩行,前後的客套話不算
        chunks = [(TERM if m.group(1) == "具體詞" else LABEL, m.group(2)) for m in matched]
    else:
        chunks = [(TERM, line) for line in lines]
    pairs, seen = [], set()
    for kind, body in chunks:
        for w in split_keywords(body):
            if w not in seen:
                seen.add(w)
                pairs.append((w, kind))
    return pairs


def character_names(db: Session, character_id: int) -> list[str]:
    """這條線的角色名:log 的發話者扣掉系統訊息(Scene (start)、Environment (system) 這類帶括號的)。"""
    return [s for s in get_senders(db, character_id) if "(" not in s]


def _existing_keywords_text(others) -> str:
    lines = [f"- {c.title or '(無標題)'}：{c.keywords.strip()}" for c in others if (c.keywords or "").strip()]
    return "\n".join(lines) if lines else "(目前沒有)"


def suggest_keywords(db: Session, context_id: int) -> KeywordSuggestion:
    ctx = get_context(db, context_id)
    if ctx is None:
        raise ContextNotFoundError(context_id)

    others = [
        c for c in get_contexts_by_character(db, ctx.character_id)
        if c.context_id != ctx.context_id and c.is_active
    ]
    used_elsewhere = {w for c in others for w in split_keywords(c.keywords)}
    other_contents = [c.context_content for c in others]
    names = character_names(db, ctx.character_id)

    rendered = load_prompt(
        KEYWORD_PROMPT,
        db,
        ctx.character_id,
        {
            "context_content": ctx.context_content,
            "existing_keywords": _existing_keywords_text(others),
            "character_names": "、".join(names) if names else "(無)",
        },
    )

    client = ai_client.get_client(config.keywords_model())
    warnings: list[str] = []
    pairs: list[tuple[str, str]] = []
    usage = TokenUsage()
    for _ in range(2):  # 格式沒照做(候選太少)重試一次
        result = client.generate(rendered.prompt, rendered.system, thinking_level=config.keywords_thinking_level())
        usage = result.usage
        pairs = [(w, k) for w, k in parse_candidates(result.text) if len(w) <= CANDIDATE_MAX_CHARS]
        if len(pairs) >= MIN_CANDIDATES:
            break
    else:
        warnings.append(f"AI 只給了 {len(pairs)} 個可用的候選詞")

    return KeywordSuggestion(
        candidates=[
            Candidate(
                text=w,
                kind=kind,
                used_elsewhere=w in used_elsewhere,
                mentioned_elsewhere=any(w in text for text in other_contents),
                has_name=any(n in w for n in names),
            )
            for w, kind in pairs
        ],
        usage=usage,
        warnings=warnings,
    )
