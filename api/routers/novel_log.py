from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session
from util.db_util import get_db
from service.novel_log_service import parse_and_import
from util.crud.novel_log import get_novel_logs
from datetime import datetime
from api.schemas import NovelLogResponse

router = APIRouter(prefix="/novel_logs", tags=["novel_logs"])


# 接檔案or接路徑直接讀檔
# (...)的寫法 -> 表示必填
# 沒指定預設值的參數要在有指定的前面
@router.post("/import")
async def import_log(
    file: UploadFile = File(...),
    character_id: int = Query(...),
    user_name: str = Query(...),
    db: Session = Depends(get_db),
):
    content_byte = await file.read()  # byte
    content = content_byte.decode("utf-8")  # 轉string
    import_cnt = parse_and_import(character_id, user_name, content, db)
    return {"import_cnt": import_cnt}


@router.get("/", response_model=list[NovelLogResponse])
def get_logs_by_character(
    character_id: int,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    db: Session = Depends(get_db),
):
    logs = get_novel_logs(db, character_id, range_start, range_end)

    return logs
