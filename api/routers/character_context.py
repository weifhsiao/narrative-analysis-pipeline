from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.errors import or_404
from util.db_util import get_db
from util.models import CharacterContext
from api.schemas import (
    ContextCreate,
    ContextUpdate,
    ContextResponse,
    ContextListItem,
    ContextReorder,
    KeywordSuggestionResponse,
)
from service.keyword_service import (
    KEYWORD_SEPARATOR,
    KEYWORDS_MAX_CHARS,
    ContextNotFoundError,
    suggest_keywords,
)
from service.character_context_service import GroupMismatchError, reorder_contexts
from service.prompt_service import PromptNotFoundError
from util.ai_client import AIBlockedError
from util.crud.character_context import (
    create_context,
    get_context,
    get_contexts_by_character,
    update_context,
)
from util.crud.character import get_character

router = APIRouter(prefix="/character_contexts", tags=["character_contexts"])


@router.post("/", response_model=ContextResponse)
def create(context_create: ContextCreate, db: Session = Depends(get_db)):
    character_id = context_create.character_id
    or_404(get_character(db, character_id), "Character", character_id)
    ctx = CharacterContext(**context_create.model_dump())
    return create_context(db, ctx)


@router.get("/", response_model=list[ContextListItem])
def list_by_character(character_id: int, db: Session = Depends(get_db)):
    return get_contexts_by_character(db, character_id)


# 排序模式整組重排:一個 request 一個交易,不更新 updated_at(「更新」只代表內容被改過)。
# 要排在 /{context_id} 之前,路徑才不會被當成 context_id
@router.put("/order", response_model=list[ContextListItem])
def reorder(body: ContextReorder, db: Session = Depends(get_db)):
    or_404(get_character(db, body.character_id), "Character", body.character_id)
    try:
        return reorder_contexts(db, body.character_id, body.context_type, body.context_ids)
    except GroupMismatchError as e:
        raise HTTPException(
            status_code=409,
            detail={"message": "context_ids 必須剛好是整組(含停用)", "missing": e.missing, "extra": e.extra},
        )


@router.get("/{context_id}", response_model=ContextResponse)
def get_detail(context_id: int, db: Session = Depends(get_db)):
    return or_404(get_context(db, context_id), "Context", context_id)


@router.patch("/{context_id}", response_model=ContextResponse)
def update(
    context_id: int, context_update: ContextUpdate, db: Session = Depends(get_db)
):
    changes = context_update.model_dump(exclude_unset=True)  # 只拿前端真的有送的欄位
    return or_404(update_context(db, context_id, changes), "Context", context_id)


# 遊戲檢索關鍵字建議:只回候選,不寫入(採用與否由使用者在 UI 決定後走 PATCH)
@router.post("/{context_id}/suggest-keywords", response_model=KeywordSuggestionResponse)
def suggest(context_id: int, db: Session = Depends(get_db)):
    try:
        result = suggest_keywords(db, context_id)
    except ContextNotFoundError:
        or_404(None, "Context", context_id)
    except PromptNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except AIBlockedError as e:
        raise HTTPException(status_code=502, detail=f"AI 沒有回傳內容:{e}")
    except Exception as e:  # provider 錯誤(金鑰、網路、額度)統一回 502,訊息給使用者看
        raise HTTPException(status_code=502, detail=f"呼叫 AI 失敗:{e}")
    return {
        "candidates": [asdict(c) for c in result.candidates],
        "max_chars": KEYWORDS_MAX_CHARS,
        "separator": KEYWORD_SEPARATOR,
        "model": result.usage.model,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "warnings": result.warnings,
    }
