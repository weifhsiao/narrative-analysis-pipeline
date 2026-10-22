"""補建缺少的資料表與索引,不動既有資料(seed 會清空,這支不會)。用法:python -m util.migration"""
from sqlalchemy.exc import IntegrityError

from util.db_util import engine
from util.models import Base


def init_db():
    Base.metadata.create_all(engine)
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
