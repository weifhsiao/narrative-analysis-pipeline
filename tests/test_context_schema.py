"""context_type charset：只能 [a-z0-9_]，先 trim 再檢查，PATCH 沒送不檢查。"""
import pytest
from pydantic import ValidationError

from api.schemas import ContextCreate, ContextUpdate
from tests.helpers import add_character


def _create(context_type: str) -> ContextCreate:
    return ContextCreate(character_id=1, context_type=context_type, context_content="x")


@pytest.mark.parametrize("context_type", ["relationship", "timeline2", "my_type", "a"])
def test_valid_context_type_accepted(context_type):
    assert _create(context_type).context_type == context_type


def test_context_type_trimmed_before_check():
    assert _create("  relationship \n").context_type == "relationship"


@pytest.mark.parametrize(
    "context_type",
    ["關係", "Relationship", "my-type", "my type", "", "   ", "type!"],
)
def test_invalid_context_type_rejected_on_create(context_type):
    with pytest.raises(ValidationError):
        _create(context_type)


def test_update_without_context_type_skips_check():
    assert ContextUpdate(context_content="只改內容").context_type is None


def test_invalid_context_type_rejected_on_update():
    with pytest.raises(ValidationError):
        ContextUpdate(context_type="Bad-Type")


def test_api_rejects_invalid_context_type_with_422(client, db):
    cid = add_character(db)

    res = client.post(
        "/character_contexts/",
        json={"character_id": cid, "context_type": "壞的", "context_content": "x"},
    )

    assert res.status_code == 422


def test_api_accepts_valid_context_type(client, db):
    cid = add_character(db)

    res = client.post(
        "/character_contexts/",
        json={"character_id": cid, "context_type": " relationship ", "context_content": "x"},
    )

    assert res.status_code == 200
    assert res.json()["context_type"] == "relationship"
