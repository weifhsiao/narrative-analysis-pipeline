import re
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime, timedelta, timezone
from util.models import CONTEXT_TYPE_PATTERN


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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


# log 的時間一律是台灣本地時間(無時區);台灣沒有日光節約,固定 +8
LOG_TIMEZONE = timezone(timedelta(hours=8))


class RunCreate(BaseModel):
    character_id: int
    range_type: int
    range_start: datetime
    range_end: datetime

    # 範圍要跟 raw_log_time 比:帶時區的(例如 Swagger 預設的 UTC `...Z`)換成台灣時間再拿掉時區,
    # 並截到秒,存進 run 表的字串才會跟其他筆同一種格式(#14)
    @field_validator("range_start", "range_end")
    @classmethod
    def _to_local_naive(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            v = v.astimezone(LOG_TIMEZONE).replace(tzinfo=None)
        return v.replace(microsecond=0)


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
    system_snapshot: str | None
    prompt_snapshot: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None

    model_config = ConfigDict(from_attributes=True)  # 讓 Pydantic 讀 ORM 物件


class ContextModify(BaseModel):
    # trim:字串前後空白去掉(None 不動)
    @field_validator("context_type", "context_content", "title", "keywords", check_fields=False)
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    # charset:定義在 _strip 之後,先 trim 再檢查(None = PATCH 沒送,不檢查)
    @field_validator("context_type", check_fields=False)
    @classmethod
    def _check_context_type(cls, v):
        if v is not None and not re.fullmatch(CONTEXT_TYPE_PATTERN, v):
            raise ValueError("context_type 只能用小寫英文、數字、底線 [a-z0-9_]")
        return v


class ContextCreate(ContextModify):
    character_id: int
    context_type: str
    context_content: str
    sort_order: int = 0
    title: str | None = None
    keywords: str | None = None


class ContextUpdate(ContextModify):
    context_type: str | None = None
    context_content: str | None = None
    sort_order: int | None = None
    title: str | None = None
    keywords: str | None = None
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


class KeywordCandidate(BaseModel):
    text: str
    kind: str  # term = 具體詞,label = 事件標籤
    used_elsewhere: bool  # 同線其他段的關鍵字已用過
    mentioned_elsewhere: bool  # 同線其他段的內容也有出現
    has_name: bool  # 含角色名


class KeywordSuggestionResponse(BaseModel):
    candidates: list[KeywordCandidate]
    max_chars: int  # 遊戲端欄位上限(含分隔符)
    separator: str
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    warnings: list[str]


class ContextResponse(ContextListItem):
    context_content: str
    keywords: str | None = None
