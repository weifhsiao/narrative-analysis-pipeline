from typing import TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def or_404(obj: T | None, kind: str, obj_id: int) -> T:
    """查不到就回 404,訊息格式統一:`Run [3] not found.`"""
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{kind} [{obj_id}] not found.")
    return obj
