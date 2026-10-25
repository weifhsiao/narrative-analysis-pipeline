"""排序模式整組重排 PUT /character_contexts/order:sort_order 寫成 0..n-1、不動 updated_at,對不上整組就整筆不寫。"""
from datetime import datetime

from sqlalchemy import select

from tests.helpers import add_character, add_context
from util.models import CharacterContext

OLD = datetime(2020, 1, 1, 12, 0, 0)


def _group(db, cid, *, inactive_last=False):
    """建一組 timeline 三筆(sort_order 0,1,2),updated_at 設成固定的舊時間。"""
    ids = [
        add_context(db, cid, "timeline", f"第{n}筆", sort_order=n, active=not (inactive_last and n == 2))
        for n in range(3)
    ]
    for c in db.execute(select(CharacterContext)).scalars():
        c.updated_at = OLD
    db.flush()
    return ids


def _put(client, cid, ids, context_type="timeline"):
    return client.put(
        "/character_contexts/order",
        json={"character_id": cid, "context_type": context_type, "context_ids": ids},
    )


def _state(db, ids):
    db.expire_all()
    return [(db.get(CharacterContext, i).sort_order, db.get(CharacterContext, i).updated_at) for i in ids]


def test_reorder_writes_order_and_returns_group(client, db):
    cid = add_character(db)
    a, b, c = _group(db, cid)
    res = _put(client, cid, [c, a, b])
    assert res.status_code == 200
    assert [(it["context_id"], it["sort_order"]) for it in res.json()] == [(c, 0), (a, 1), (b, 2)]
    assert [s for s, _ in _state(db, [c, a, b])] == [0, 1, 2]


def test_reorder_keeps_updated_at(client, db):
    cid = add_character(db)
    a, b, c = _group(db, cid)
    res = _put(client, cid, [b, c, a])
    assert all(it["updated_at"] == OLD.isoformat() for it in res.json())
    assert [u for _, u in _state(db, [a, b, c])] == [OLD, OLD, OLD]


def test_reorder_requires_inactive_too(client, db):
    cid = add_character(db)
    a, b, c = _group(db, cid, inactive_last=True)
    res = _put(client, cid, [b, a])
    assert res.status_code == 409
    assert res.json()["detail"]["missing"] == [c]
    assert res.json()["detail"]["extra"] == []
    assert _put(client, cid, [b, a, c]).status_code == 200


def test_reorder_rejects_foreign_ids_and_writes_nothing(client, db):
    cid = add_character(db)
    other = add_character(db, "別人")
    a, b, c = _group(db, cid)
    foreign = add_context(db, other, "timeline", "別人的")
    other_type = add_context(db, cid, "scenario", "別的類型")
    before = _state(db, [a, b, c])

    res = _put(client, cid, [c, b, a, foreign, other_type])
    assert res.status_code == 409
    assert res.json()["detail"]["missing"] == []
    assert res.json()["detail"]["extra"] == sorted([foreign, other_type])

    res = _put(client, cid, [c, b, foreign])  # 換掉一筆:兩邊都有
    assert res.status_code == 409
    assert res.json()["detail"]["missing"] == [a]
    assert res.json()["detail"]["extra"] == [foreign]
    assert _state(db, [a, b, c]) == before


def test_reorder_rejects_empty_and_duplicates(client, db):
    cid = add_character(db)
    a, b, c = _group(db, cid)
    assert _put(client, cid, []).status_code == 422
    assert _put(client, cid, [a, a, b, c]).status_code == 422
    assert _put(client, cid, [a, b, c], context_type="Time-Line").status_code == 422


def test_reorder_404_when_character_missing(client):
    res = _put(client, 999, [1])
    assert res.status_code == 404
    assert res.json()["detail"] == "Character [999] not found."


def test_single_patch_of_sort_order_still_bumps_updated_at(client, db):
    cid = add_character(db)
    a, _, _ = _group(db, cid)
    res = client.patch(f"/character_contexts/{a}", json={"sort_order": 5})
    assert res.status_code == 200
    assert datetime.fromisoformat(res.json()["updated_at"]) > OLD
