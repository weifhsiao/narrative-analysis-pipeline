from fastapi import APIRouter, Depends, HTTPException
from api.schemas import RunCreate, RunResponse
from sqlalchemy.orm import Session
from util.db_util import get_db
from util.crud.run import create_run, get_run, get_runs_by_character
from util.models import Run
from service.pipeline_service import run_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])
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


@router.post("/{run_id}/execute")
def execute(run_id: int, db: Session = Depends(get_db)):
    # 先查Run是否存在
    run = get_run(db, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run id [{run_id}] not found.")

    character_id = run.character_id
    range_start = run.range_start
    range_end = run.range_end
    insert_cnt = run_pipeline(db, run_id, f"{character_id}", range_start, range_end)

    return {"insert_cnt": insert_cnt}


@router.post("/{run_id}/preview")
def preview(run_id: int, db: Session = Depends(get_db)):
    # 只組 prompt 並寫出 debug 檔，不打 AI、不入庫
    run = get_run(db, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run id [{run_id}] not found.")

    return run_pipeline(
        db,
        run_id,
        f"{run.character_id}",
        run.range_start,
        run.range_end,
        preview=True,
    )


@router.get("/{run_id}", response_model=RunResponse)
def get_run_by_id(run_id: int, db: Session = Depends(get_db)):
    run = get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run id [{run_id}] not found.")

    return run


@router.get("/", response_model=list[RunResponse])
def list_runs(character_id: int, db: Session = Depends(get_db)):
    runs = get_runs_by_character(db, character_id)

    return runs
