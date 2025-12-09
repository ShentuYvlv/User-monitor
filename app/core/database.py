from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    pool_pre_ping=True,
    # 针对低配服务器的优化配置
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出连接数
    pool_recycle=3600,    # 连接回收时间
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency for API
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
