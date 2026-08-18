"""数据库连接与会话管理。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

DB_URL = settings.DB_URL

# 本地 SQLite：确保数据目录存在
if DB_URL.startswith("sqlite"):
    os.makedirs(settings.DB_DIR, exist_ok=True)
    engine = create_engine(
        DB_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # PostgreSQL（Supabase 等）：psycopg2 驱动，无需 check_same_thread
    engine = create_engine(DB_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：为每个请求提供独立的数据库会话，请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
