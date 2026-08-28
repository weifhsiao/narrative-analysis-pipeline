from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime


class CharacterCreate(BaseModel):
    name: str


class CharacterResponse(BaseModel):
    character_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


class NovelLogResponse(BaseModel):
    novel_log_id: int
    character_id: int
    raw_log_time: datetime
    sender: str
    content: str
    page: str | None = None
    story_date: str | None = None
    story_time: str | None = None
    raw_location: str | None = None
    is_spinoff: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


class RunCreate(BaseModel):
    character_id: int
    range_type: int
    range_start: datetime
    range_end: datetime


class RunResponse(BaseModel):
    run_id: int
    character_id: int
    range_type: int
    range_start: str
    range_end: str
    exec_cnt: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


class PromptExecResponse(BaseModel):
    prompt_exec_id: int
    run_id: int
    prompt_id: int | None
    parent_exec_id: int | None
    start_time: datetime
    end_time: datetime | None
    result_code: str | None
    result_content: str | None

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


class ContextModify(BaseModel):
    # trim:字串前後空白去掉(None 不動)
    @field_validator("context_type", "context_content", "title", check_fields=False)
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ContextCreate(ContextModify):
    character_id: int
    context_type: str
    context_content: str
    sort_order: int = 0
    title: str | None = None


class ContextUpdate(ContextModify):
    context_type: str | None = None
    context_content: str | None = None
    sort_order: int | None = None
    title: str | None = None
    is_active: bool = True


class ContextListItem(BaseModel):
    context_id: int
    character_id: int
    context_type: str
    sort_order: int
    title: str | None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextResponse(ContextListItem):
    context_content: str
