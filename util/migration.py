"""補建缺少的資料表、欄位與索引,不動既有資料(seed 會清空,這支不會)。用法:python -m util.migration"""
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from util.db_util import engine
from util.models import Base


def add_missing_columns() -> list[str]:
    """既有的表補上後來新增的欄位。只處理可為 NULL 的欄位(SQLite 的 ADD COLUMN 不能直接加 NOT NULL),
    其他的停下來說明,不猜預設值。回傳補上的「表.欄位」。"""
    added = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            if not column.nullable:
                raise SystemExit(
                    f"{table.name}.{column.name} 是 NOT NULL,不能自動補欄位,請另寫遷移腳本。"
                )
            col_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
            added.append(f"{table.name}.{column.name}")
    return added


def init_db():
    Base.metadata.create_all(engine)
    for name in add_missing_columns():
        print(f"補上欄位 {name}")
    # create_all 只會替「新建的表」建索引;既有的表補上後來新增的索引
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            try:
                index.create(engine, checkfirst=True)
            except IntegrityError as e:
                raise SystemExit(
                    f"無法建立唯一索引 {index.name}:{table.name} 已有重複資料,請先清掉重複再重跑。\n{e.orig}"
                )


if __name__ == "__main__":
    init_db()
    print("建表完成！")
