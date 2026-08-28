from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
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
    page = Column(String)
    story_date = Column(String)
    story_time = Column(String)
    raw_location = Column(String)
    is_spinoff = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class PromptTemplate(Base):
    __tablename__ = "prompt_template"
    prompt_id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_name = Column(String)
    system_instruction = Column(String)
    prompt = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

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

    parent = relationship("PromptExecution", remote_side=[prompt_exec_id])


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
