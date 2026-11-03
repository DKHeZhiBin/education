from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.session import LearningSession


class MediaAsset(UuidPrimaryKeyMixin, Base):
    """中文：定义“media·asset”类，封装该职责相关的数据与行为。
    English: Defines the media asset class and encapsulates data and behavior for that responsibility.
    """
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("idx_media_session_created", "session_id", "created_at"),
        Index("idx_media_owner_created", "owner_user_id", "created_at"),
        Index("idx_media_expiry", "expires_at"),
    )

    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=True
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    ocr_original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    recognized_formulas: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    formula_validation_status: Mapped[str] = mapped_column(
        String(20), default="not_checked", nullable=False
    )
    formula_validation_issues: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    student_confirmed_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False
    )

    session: Mapped[LearningSession | None] = relationship(back_populates="media_assets")
    owner: Mapped[User] = relationship()
