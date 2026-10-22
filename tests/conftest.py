"""測試共用設定：切斷所有真實資源，測試只碰記憶體 DB 與 tmp_path。

- DB：每個測試一個全新的 in-memory SQLite；真正的 data/novel.db 一旦被連線就直接報錯。
- 檔案：file_util 的 BASE_DIR 指到 tmp_path，不寫 data/。prompt 一律從記憶體 DB 讀（helpers.add_prompt）。
- AI：pipeline 的 get_client 換成 FakeAIClient，永遠不打外部 API。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import service.pipeline_service as pipeline_service
import util.db_util as db_util
import util.file_util as file_util
from util.ai_client import AIClient, Attachment, GenerateResult, TokenUsage
from util.models import Base


# do_connect 在 sqlite3.connect() 之前觸發：擋下時連檔案都不會被開啟或建立
@event.listens_for(db_util.engine, "do_connect")
def _refuse_real_db(*_):
    raise RuntimeError("測試不得連線真實 DB（data/novel.db），請用 db fixture")


FAKE_USAGE = TokenUsage(model="fake-model-001", input_tokens=100, output_tokens=30, thinking_tokens=10)


class FakeAIClient(AIClient):
    """記錄每次呼叫；response 可改成字串或 Exception 來模擬各種結果。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.response: str | Exception = "fake response"
        self.usage = FAKE_USAGE

    def generate(
        self,
        prompt: str,
        system_instruction: str,
        attachments: list[Attachment] | None = None,
    ) -> GenerateResult:
        self.calls.append(
            {"prompt": prompt, "system": system_instruction, "attachments": attachments}
        )
        if isinstance(self.response, Exception):
            raise self.response
        return GenerateResult(text=self.response, usage=self.usage)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(file_util, "BASE_DIR", tmp_path)
    # .env 可能在 import 時塞了值，每個測試回到已知狀態
    monkeypatch.delenv("LOG_INPUT_MODE", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "test-model")


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch) -> FakeAIClient:
    client = FakeAIClient()
    monkeypatch.setattr(pipeline_service, "get_client", lambda: client)
    return client


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine)
    # 萬一有程式繞過 fixture 直接用 SessionLocal，也只會拿到記憶體 DB
    monkeypatch.setattr(db_util, "SessionLocal", session_factory)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db):
    from api.app import app

    def _override_get_db():
        yield db

    # 只交出同一個 session，不 commit/rollback，測試才能在同一交易內查到 router 寫的資料；
    # 真正 get_db 的 commit/rollback 由 test_db_util 另外測
    app.dependency_overrides[db_util.get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(db_util.get_db, None)
