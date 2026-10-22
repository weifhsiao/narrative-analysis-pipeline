"""context 的遊戲檢索關鍵字建議:把這段內容與同線其他段已用的關鍵字交給 AI,回傳候選詞讓使用者挑。

只建議不寫入:要不要採用、怎麼組合由使用者在 UI 決定,存檔走一般的 PATCH。
prompt 在 prompts/keywords.txt(跟 pipeline 的 prompt 一樣入庫、有版本)。
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import util.ai_client as ai_client
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


class ContextNotFoundError(LookupError):
    pass


@dataclass
class Candidate:
    text: str
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

    client = ai_client.get_client()
    warnings: list[str] = []
    words: list[str] = []
    usage = TokenUsage()
    for _ in range(2):  # 格式沒照做(候選太少)重試一次
        result = client.generate(rendered.prompt, rendered.system)
        usage = result.usage
        words = [w for w in split_keywords(result.text) if len(w) <= CANDIDATE_MAX_CHARS]
        if len(words) >= MIN_CANDIDATES:
            break
    else:
        warnings.append(f"AI 只給了 {len(words)} 個可用的候選詞")

    return KeywordSuggestion(
        candidates=[
            Candidate(
                text=w,
                used_elsewhere=w in used_elsewhere,
                mentioned_elsewhere=any(w in text for text in other_contents),
                has_name=any(n in w for n in names),
            )
            for w in words
        ],
        usage=usage,
        warnings=warnings,
    )
