from fastapi import APIRouter, Depends, HTTPException
from api.schemas import RunCreate, RunResponse, PromptExecResponse
from sqlalchemy.orm import Session
from api.errors import or_404
from util.db_util import get_db
from util.crud.run import create_run, get_run, get_runs_by_character
from util.crud.prompt import get_prompt_executions_by_run
from util.models import Run
from service.pipeline_service import run_pipeline
from service.prompt_service import PromptLintError

router = APIRouter(prefix="/runs", tags=["runs"])


def _lint_failed(e: PromptLintError) -> HTTPException:
    # prompt 標籤對不上:跑下去送的 prompt 會缺內容,回 422 並列出每條 ERROR
    return HTTPException(
        status_code=422,
        detail={
            "error": "prompt lint failed",
            "issues": [{"prompt": i.prompt, "message": i.message} for i in e.issues],
        },
    )
# POST /runs 建立run資料
# POST /runs/{run_id}/execute 跑pipeline
# GET  /runs/{run_id} 回傳 run 資料 + 底下所有 prompt_executions
# GET  /runs?character_id=1 查角色的run結果


@router.post("/", response_model=RunResponse)
def create(run_create: RunCreate, db: Session = Depends(get_db)):
    run = Run(
        character_id=run_create.character_id,
        range_type=run_create.range_type,
        range_start=run_create.range_start,
        range_end=run_create.range_end,
    )
    run = create_run(db, run)

    return run


def _run_pipeline(db: Session, run_id: int, preview: bool):
    # execute / preview 共用:查 run → 跑 pipeline → lint 失敗轉 422
    run = or_404(get_run(db, run_id), "Run", run_id)
    try:
        return run_pipeline(
            db, run_id, run.character_id, run.range_start, run.range_end, preview=preview
        )
    except PromptLintError as e:
        raise _lint_failed(e)


@router.post("/{run_id}/execute")
def execute(run_id: int, db: Session = Depends(get_db)):
    return {"insert_cnt": _run_pipeline(db, run_id, preview=False)}


@router.post("/{run_id}/preview")
def preview(run_id: int, db: Session = Depends(get_db)):
    # 只組 prompt 並回傳實際會送出的內容，不打 AI、不寫檔、不入庫
    return _run_pipeline(db, run_id, preview=True)


@router.get("/{run_id}", response_model=RunResponse)
def get_run_by_id(run_id: int, db: Session = Depends(get_db)):
    return or_404(get_run(db, run_id), "Run", run_id)


@router.get("/", response_model=list[RunResponse])
def list_runs(character_id: int, db: Session = Depends(get_db)):
    runs = get_runs_by_character(db, character_id)

    return runs


@router.get("/{run_id}/execution", response_model=list[PromptExecResponse])
def get_exec_detail_by_id(run_id: int, db: Session = Depends(get_db)):
    execs = get_prompt_executions_by_run(db, run_id)
    return execs
