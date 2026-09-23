from sqlalchemy.orm import Session
from util.crud.character_context import get_active_contexts_by_type


def load_context(db: Session, character_id: int, context_type: str) -> str:
    """撈某角色某 type 的 active context，依 sort_order 組成單一字串。

    通用、不綁 type：單筆就是它自己，多筆依序以空行 join。查無回空字串。
    """
    contexts = get_active_contexts_by_type(db, int(character_id), context_type)
    return "\n\n".join(c.context_content for c in contexts)
