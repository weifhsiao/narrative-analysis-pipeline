"""router 共用行為:404 訊息格式、run 的 exec_cnt。"""
import pytest

from tests.helpers import add_character, add_run
from util.models import PromptExecution


@pytest.mark.parametrize(
    "method, url, kind",
    [
        ("get", "/characters/999", "Character"),
        ("get", "/character_contexts/999", "Context"),
        ("patch", "/character_contexts/999", "Context"),
        ("get", "/runs/999", "Run"),
        ("post", "/runs/999/execute", "Run"),
        ("post", "/runs/999/preview", "Run"),
    ],
)
def test_404_detail_format(client, method, url, kind):
    kwargs = {"json": {}} if method == "patch" else {}
    res = getattr(client, method)(url, **kwargs)
    assert res.status_code == 404
    assert res.json()["detail"] == f"{kind} [999] not found."


def test_create_context_404_when_character_missing(client):
    res = client.post(
        "/character_contexts/",
        json={"character_id": 999, "context_type": "timeline", "context_content": "x"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Character [999] not found."


def test_run_exec_cnt(client, db):
    cid = add_character(db)
    busy = add_run(db, cid, "2026-06-20 00:00:00", "2026-06-21 00:00:00")
    idle = add_run(db, cid, "2026-06-22 00:00:00", "2026-06-23 00:00:00")
    other = add_run(db, add_character(db, "別人"), "2026-06-20 00:00:00", "2026-06-21 00:00:00")
    db.add_all([PromptExecution(run_id=busy), PromptExecution(run_id=busy)])
    db.flush()

    assert client.get(f"/runs/{busy}").json()["exec_cnt"] == 2
    assert client.get(f"/runs/{idle}").json()["exec_cnt"] == 0
    listed = {r["run_id"]: r["exec_cnt"] for r in client.get("/runs/", params={"character_id": cid}).json()}
    assert listed == {busy: 2, idle: 0}
    assert other not in listed
