from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.session import LearningSession


class MediaAsset(UuidPrimaryKeyMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("idx_media_session_created", "session_id", "created_at"),
        Index("idx_media_expiry", "expires_at"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    session: Mapped[LearningSession] = relationship(back_populates="media_assets")
    owner: Mapped[User] = relationship()
