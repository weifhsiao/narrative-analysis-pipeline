"""補建缺少的資料表,不動既有資料(seed 會清空,這支不會)。用法:python -m util.migration"""
from util.db_util import engine
from util.models import Base


def init_db():
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("建表完成！")
