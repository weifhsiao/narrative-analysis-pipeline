"""把 data/{character_id}/ 底下的 relationship/timeline/scenarios 檔遷移進 character_context 表。
用法:
    python migrate_context.py <character_id>            # dry-run,只預覽
    python migrate_context.py <character_id> --write     # 真的寫入
略過 bk/(備份)。已存在 context 的角色預設中止(避免重複),--force 才覆寫式再塞。
"""
import sys
from pathlib import Path
from util.db_util import SessionLocal
from util.models import CharacterContext

BASE = Path("./data")

TYPE_TITLE = {"relationship": "關係狀態總結", "timeline": "時間軸"}


def roman(n: int) -> str:
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
             (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
             (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in table:
        while n >= v:
            out += s; n -= v
    return out


def build_rows(character_id: int) -> list[CharacterContext]:
    root = BASE / str(character_id)
    rows: list[CharacterContext] = []

    # relationship / timeline:單檔,sort_order=0,title=None
    for ctype in ("relationship", "timeline"):
        f = root / f"{ctype}.txt"
        if f.exists():
            content = f.read_text(encoding="utf-8").strip()
            if content:
                rows.append(CharacterContext(
                    character_id=character_id, context_type=ctype,
                    context_content=content, sort_order=0, title=TYPE_TITLE[ctype],
                ))

    # scenarios:多檔,照檔名排,sort_order=1..n,title=檔名(scenario1..)
    scenario_dir = root / "scenarios"
    if scenario_dir.exists():
        for i, f in enumerate(sorted(scenario_dir.glob("*.txt")), start=1):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                rows.append(CharacterContext(
                    character_id=character_id, context_type="scenario",
                    context_content=content, sort_order=i, title=f"發生過的劇情 {roman(i)}",
                ))
    return rows


def main():
    if len(sys.argv) < 2:
        print("需要 character_id"); sys.exit(1)
    character_id = int(sys.argv[1])
    write = "--write" in sys.argv
    force = "--force" in sys.argv

    rows = build_rows(character_id)
    print(f"=== character_id={character_id} 準備遷移 {len(rows)} 筆 ===")
    for r in rows:
        preview = r.context_content.replace("\n", " ")[:40]
        print(f"  [{r.context_type:12}] sort={r.sort_order} title={r.title!r:15} "
              f"len={len(r.context_content):5}  「{preview}…」")

    db = SessionLocal()
    try:
        existing = db.query(CharacterContext).filter(
            CharacterContext.character_id == character_id).count()
        if existing and not force:
            print(f"\n⚠️ 該角色已有 {existing} 筆 context,中止(要覆寫式再塞請加 --force)。")
            return

        if not write:
            print("\n[DRY-RUN] 沒有寫入。確認無誤後加 --write 實際執行。")
            return

        db.add_all(rows)
        db.commit()
        print(f"\n✅ 已寫入 {len(rows)} 筆。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
