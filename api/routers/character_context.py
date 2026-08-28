from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from util.db_util import get_db
from util.models import CharacterContext
from api.schemas import ContextCreate, ContextUpdate, ContextResponse, ContextListItem
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
    character = get_character(db, character_id)

    if character is None:
        raise HTTPException(
            status_code=404, detail=f"Character [{character_id}] not found."
        )

    ctx = CharacterContext(**context_create.model_dump())
    return create_context(db, ctx)


@router.get("/", response_model=list[ContextListItem])
def list_by_character(character_id: int, db: Session = Depends(get_db)):
    return get_contexts_by_character(db, character_id)


@router.get("/{context_id}", response_model=ContextResponse)
def get_detail(context_id: int, db: Session = Depends(get_db)):
    ctx = get_context(db, context_id)
    if ctx is None:
        raise HTTPException(
            status_code=404, detail=f"Context [{context_id}] not found."
        )
    return ctx


@router.patch("/{context_id}", response_model=ContextResponse)
def update(
    context_id: int, context_update: ContextUpdate, db: Session = Depends(get_db)
):
    changes = context_update.model_dump(exclude_unset=True)  # 只拿前端真的有送的欄位
    ctx = update_context(db, context_id, changes)
    if ctx is None:
        raise HTTPException(
            status_code=404, detail=f"Context [{context_id}] not found."
        )
    return ctx
