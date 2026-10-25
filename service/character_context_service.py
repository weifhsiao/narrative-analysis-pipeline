from sqlalchemy.orm import Session
from util.crud.character_context import (
    get_active_contexts_by_type,
    get_contexts_by_type,
    set_sort_orders,
)
from util.models import CharacterContext


def load_context(db: Session, character_id: int, context_type: str) -> str:
    """撈某角色某 type 的 active context，依 sort_order 組成單一字串。

    通用、不綁 type：單筆就是它自己，多筆依序以空行 join。查無回空字串。
    """
    contexts = get_active_contexts_by_type(db, int(character_id), context_type)
    return "\n\n".join(c.context_content for c in contexts)


class GroupMismatchError(ValueError):
    """送來的 id 跟目前整組對不上。missing = 組裡有但沒送;extra = 送了但不在組裡。"""

    def __init__(self, missing: list[int], extra: list[int]):
        super().__init__(f"context_ids 必須剛好是整組(含停用):missing={missing} extra={extra}")
        self.missing = missing
        self.extra = extra


def reorder_contexts(
    db: Session, character_id: int, context_type: str, context_ids: list[int]
) -> list[CharacterContext]:
    """整組重排 sort_order,不動 updated_at。先比對完才寫,對不上就整筆不寫。"""
    group = get_contexts_by_type(db, character_id, context_type)
    current = {c.context_id for c in group}
    sent = set(context_ids)
    if current != sent:
        raise GroupMismatchError(sorted(current - sent), sorted(sent - current))
    set_sort_orders(db, context_ids)
    return get_contexts_by_type(db, character_id, context_type)
