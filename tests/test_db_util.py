"""util/db_util：真 DB 防護本身，以及 get_db 的 commit / rollback。

API 測試的 client fixture 把 get_db 換成只交出 session 的替身，
真正的交易行為在這裡直接測。
"""
import pytest
from sqlalchemy import select

import util.db_util as db_util
from util.models import Character


def _names() -> list[str]:
    with db_util.SessionLocal() as s:
        return s.execute(select(Character.name)).scalars().all()


def test_connecting_real_engine_raises():
    with pytest.raises(RuntimeError, match="真實 DB"):
        db_util.engine.connect()


def test_get_db_commits_on_success(db):
    gen = db_util.get_db()
    session = next(gen)
    session.add(Character(name="留下"))
    session.flush()

    with pytest.raises(StopIteration):
        next(gen)  # router 正常結束

    assert _names() == ["留下"]


def test_get_db_rolls_back_on_exception(db):
    gen = db_util.get_db()
    session = next(gen)
    session.add(Character(name="作廢"))
    session.flush()

    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("router 失敗"))

    assert _names() == []
