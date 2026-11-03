from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache(maxsize=1)
def create_mysql_engine() -> Engine:
    """中文：处理“创建·MySQL·engine”相关操作。
    English: Handles the create mysql engine operation.
    """
    if not settings.database_url.startswith("mysql+"):
        raise ValueError("DATABASE_URL must use a SQLAlchemy MySQL driver such as mysql+pymysql")
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle_seconds,
        echo=settings.database_echo,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """中文：处理“创建·会话·工厂”相关操作。
    English: Handles the create session factory operation.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
