from models import Base
from db_util import engine


def init_db():
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("建表完成！")
