from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Character(Base):
    __tablename__ = "character"
    character_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    novel_logs = relationship("NovelLog")
    runs = relationship("Run")
    contexts = relationship("CharacterContext")


class NovelLog(Base):
    __tablename__ = "novel_log"
    novel_log_id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("character.character_id"))
    raw_log_time = Column(DateTime, nullable=False)
    sender = Column(String, nullable=False)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.now)


class PromptTemplate(Base):
    """prompt 模板,append-only:改 prompt 一律新增一版,舊版不動(所以沒有 updated_at)。

    同一支 prompt 的各版以 root_prompt_id 串起(= v1 的 prompt_id,v1 指自己),
    最新版 = 該 root 的 max(version)。prompt_execution.prompt_id 指到的是「那一版」。
    prompt_name 只當對外入口(pipeline 常數、import 對應 .txt 檔名),同一支各版一致。
    """

    __tablename__ = "prompt_template"
    __table_args__ = (UniqueConstraint("root_prompt_id", "version"),)
    prompt_id = Column(Integer, primary_key=True, autoincrement=True)
    root_prompt_id = Column(Integer, ForeignKey("prompt_template.prompt_id"))
    version = Column(Integer, nullable=False, default=1)
    prompt_name = Column(String, nullable=False)
    system_instruction = Column(String)
    prompt = Column(String)
    max_length = Column(Integer)  # eval 字數上限,隨版本走;None = 未設定
    created_at = Column(DateTime, default=datetime.now)

    prompt_executions = relationship("PromptExecution")


class Run(Base):
    __tablename__ = "run"
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("character.character_id"))
    range_type = Column(Integer, nullable=False)
    range_start = Column(String, nullable=False)
    range_end = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    prompt_executions = relationship("PromptExecution")


class PromptExecution(Base):
    __tablename__ = "prompt_execution"
    prompt_exec_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("run.run_id"))
    prompt_id = Column(Integer, ForeignKey("prompt_template.prompt_id"))
    parent_exec_id = Column(Integer, ForeignKey("prompt_execution.prompt_exec_id"))
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime)
    result_code = Column(String)
    result_content = Column(String)
    # 快照:填完 context 的 system / prompt;run 參數標籤(<log_content>)保持模板原樣,
    # log 由 run range 重建。context 事後可改,這裡記的是當輪實際用到的內容。
    system_snapshot = Column(String)
    prompt_snapshot = Column(String)
    # AI 用量:provider 中立語意,由各 AIClient 換算(見 util/ai_client.TokenUsage)
    model = Column(String)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    thinking_tokens = Column(Integer)

    parent = relationship("PromptExecution", remote_side=[prompt_exec_id])


# context_type 字元限制：小寫英文、數字、底線（以 fullmatch 使用）。
# type 名同時是 prompt 的填空標籤名 <T>；限定字元讓 lint 能分辨「填空標籤」與中文「結構標籤」。
CONTEXT_TYPE_PATTERN = r"[a-z0-9_]+"


class CharacterContext(Base):
    __tablename__ = "character_context"

    context_id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("character.character_id"))
    context_type = Column(String, nullable=False)
    context_content = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    title = Column(String)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
