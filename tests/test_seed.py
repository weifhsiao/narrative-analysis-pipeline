"""scripts.seed:fresh clone 的 Quickstart 要能不加 --force 就 import、preview 回 200;
DB 有 seed 以外的資料時,沒加 --yes 一律不動。
"""
from pathlib import Path

import pytest
from sqlalchemy import text

import scripts.seed as seed
from service.pipeline_service import PIPELINE_PROMPTS
from service.prompt_service import lint_prompts, parse_prompt_file, save_prompt
from tests.helpers import add_character, add_context, add_log
from util.models import Character, CharacterContext, NovelLog, PromptExecution, Run

PROMPT_FILES = sorted((Path(__file__).parent.parent / "prompts").glob("*.txt"))


def _seed(db):
    seed.wipe_all(db)
    seed.seed_characters(db)
    seed.seed_runs(db)
    seed.seed_prompt_executions(db)
    seed.seed_contexts(db)


def _import_prompts(db):
    for path in PROMPT_FILES:
        save_prompt(db, path.stem, *parse_prompt_file(path.read_text(encoding="utf-8")))


def _counts(db) -> dict[str, int]:
    return {
        m.__tablename__: db.query(m).count()
        for m in (Character, Run, PromptExecution, NovelLog, CharacterContext)
    }


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.stem)
def test_seeded_db_imports_real_prompts_without_force(db, path):
    _seed(db)

    # force=False:lint 有 ERROR 會丟 PromptLintError
    template, issues = save_prompt(
        db, path.stem, *parse_prompt_file(path.read_text(encoding="utf-8"))
    )

    assert template is not None
    assert [i for i in issues if i.level == "ERROR"] == []


def test_seeded_character_has_every_context_the_pipeline_uses(db):
    _seed(db)
    _import_prompts(db)

    issues = [
        i for i in lint_prompts(db, 1, PIPELINE_PROMPTS) if i.level in ("ERROR", "WARN")
    ]

    assert issues == []


def test_preview_on_seeded_run_returns_200(db, client, fake_ai):
    _seed(db)
    _import_prompts(db)

    res = client.post("/runs/1/preview")

    assert res.status_code == 200
    prompts = res.json()["prompts"]
    assert [p["prompt_name"] for p in prompts] == list(PIPELINE_PROMPTS)
    assert all(p["error"] is None for p in prompts)
    assert fake_ai.calls == []


def test_seed_is_repeatable(db):
    _seed(db)
    first = _counts(db)

    assert seed.find_foreign_data(db) == []
    _seed(db)

    assert _counts(db) == first


def test_empty_db_has_no_foreign_data(db):
    assert seed.find_foreign_data(db) == []


@pytest.mark.parametrize(
    "add_foreign, table",
    [
        (lambda db: add_character(db, "真實角色"), "character"),
        (lambda db: add_log(db, 1, "匯入的 log", "2026-06-20 21:02:11"), "novel_log"),
        (lambda db: add_context(db, 1, "relationship", "真實 context"), "character_context"),
        (lambda db: db.add(PromptExecution(run_id=1, prompt_id=3, result_content="x")), "prompt_execution"),
        # 與 seed run 相同、只有 run_id 不同(例:在範例角色上另建、還沒跑過的 run)
        (lambda db: db.add(Run(**(seed.SEED_RUNS[0] | {"run_id": 2}))), "run"),
    ],
    ids=["character", "novel_log", "context", "execution", "run"],
)
def test_foreign_data_is_reported(db, add_foreign, table):
    _seed(db)
    add_foreign(db)
    db.flush()

    found = seed.find_foreign_data(db)

    assert [line.split(":")[0] for line in found] == [table]


def test_edited_seed_context_counts_as_foreign(db):
    _seed(db)
    db.query(CharacterContext).filter_by(context_type="timeline").update(
        {"context_content": "使用者改過"}
    )

    assert seed.find_foreign_data(db) == ["character_context: 1 筆非 seed context"]


@pytest.fixture
def seed_main(db, monkeypatch):
    """讓 seed.main() 用測試的記憶體 DB(它 import 時綁了 util.db_util 的 SessionLocal/engine)。"""
    from sqlalchemy.orm import sessionmaker

    bind = db.get_bind()
    monkeypatch.setattr(seed, "SessionLocal", sessionmaker(bind))
    monkeypatch.setattr(seed, "engine", bind)

    def run(*argv):
        monkeypatch.setattr("sys.argv", ["seed", *argv])
        seed.main()

    return run


def test_main_refuses_and_touches_nothing_when_foreign_data(db, seed_main, capsys):
    cid = add_character(db, "真實角色")
    add_context(db, cid, "relationship", "真實 context")
    add_log(db, cid, "真實 log", "2026-01-01 00:00:00")
    db.commit()
    before = _counts(db)

    with pytest.raises(SystemExit) as e:
        seed_main()

    assert e.value.code == 1
    assert _counts(db) == before
    assert db.query(CharacterContext).one().context_content == "真實 context"
    assert "--yes" in capsys.readouterr().out


def test_main_with_yes_wipes_and_reseeds(db, seed_main):
    add_character(db, "真實角色")
    db.commit()

    seed_main("--yes")

    assert [(c.character_id, c.name) for c in db.query(Character).all()] == [(1, "顧望舒")]
    assert db.query(CharacterContext).count() == len(seed.SEED_CONTEXTS)
    assert seed.find_foreign_data(db) == []


def test_main_reseeds_seed_only_db_without_yes(db, seed_main):
    seed_main()
    seed_main()

    assert db.query(CharacterContext).count() == len(seed.SEED_CONTEXTS)


def test_main_refuses_old_schema_with_readable_message(db, seed_main, capsys):
    """prompt 版本化之前的 DB:prompt_execution 缺新欄位,檢查階段就讀不了。"""
    _seed(db)
    db.commit()
    db.execute(text("ALTER TABLE prompt_execution DROP COLUMN system_snapshot"))
    db.commit()
    before = db.execute(text("SELECT count(*) FROM character_context")).scalar()

    with pytest.raises(SystemExit) as e:
        seed_main("--yes")  # --yes 也一樣擋:舊 schema 寫不進範例

    out = capsys.readouterr().out
    assert e.value.code == 1
    assert "no such column: prompt_execution.system_snapshot" in out
    assert "migrate_prompt_template" in out
    assert db.execute(text("SELECT count(*) FROM character_context")).scalar() == before
