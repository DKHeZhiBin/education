from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import MetaData, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """中文：处理“utc·now”相关操作。
    English: Handles the utc now operation.
    """
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """中文：处理“new·uuid”相关操作。
    English: Handles the new uuid operation.
    """
    return str(uuid4())


MYSQL_DATETIME = DATETIME(fsp=6)


class Base(DeclarativeBase):
    """中文：定义“基础”类，封装该职责相关的数据与行为。
    English: Defines the base class and encapsulates data and behavior for that responsibility.
    """
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    """中文：定义“uuid·primary·key·mixin”类，封装该职责相关的数据与行为。
    English: Defines the uuid primary key mixin class and encapsulates data and behavior for that responsibility.
    """
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class TimestampMixin:
    """中文：定义“timestamp·mixin”类，封装该职责相关的数据与行为。
    English: Defines the timestamp mixin class and encapsulates data and behavior for that responsibility.
    """
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False
    )
