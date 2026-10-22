from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from util.db_util import get_db
from service.novel_log_service import parse_and_import
from util.parse_log_util import LogFormatError
from util.crud.novel_log import get_novel_logs
from datetime import datetime
from dataclasses import asdict
from api.schemas import NovelLogResponse, MessageImportRequest, MessageImportResponse
from service.message_import_service import Message, MessageImportError, import_messages

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
    try:
        result = parse_and_import(character_id, user_name, content, db)
    except LogFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"import_cnt": result.inserted, "skipped_cnt": result.skipped}


# 通用訊息清單匯入(任何來源轉成 sender/time/content 即可),預設 dry_run 只回報不寫入
@router.post("/import-messages", response_model=MessageImportResponse)
def import_message_list(
    body: MessageImportRequest,
    character_id: int = Query(...),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    messages = [Message(sender=m.sender, time=m.time, content=m.content) for m in body.messages]
    try:
        report = import_messages(db, character_id, messages, body.character_name, dry_run=dry_run)
    except MessageImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict(report)


@router.get("/", response_model=list[NovelLogResponse])
def get_logs_by_character(
    character_id: int,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    db: Session = Depends(get_db),
):
    logs = get_novel_logs(db, character_id, range_start, range_end)

    return logs
