from datetime import datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import MediaAsset


class ProblemImageRepository:
    """中文：定义“题目·图片·仓储”类，封装该职责相关的数据与行为。
    English: Defines the problem image repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, engine: Engine, session_factory: sessionmaker[Session]) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.engine = engine
        self.session_factory = session_factory

    def create(
        self,
        *,
        asset_id: str,
        owner_user_id: str,
        storage_key: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        content_sha256: str,
        expires_at: datetime,
    ) -> MediaAsset:
        """中文：处理“创建”相关操作。
        English: Handles the create operation.
        """
        with self.session_factory.begin() as db:
            entity = MediaAsset(
                id=asset_id,
                session_id=None,
                owner_user_id=owner_user_id,
                media_type="image",
                storage_key=storage_key,
                original_filename=original_filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                content_sha256=content_sha256,
                processing_status="pending",
                expires_at=expires_at,
            )
            db.add(entity)
            db.flush()
            db.refresh(entity)
            return entity

    def get_owned(self, asset_id: str, owner_user_id: str) -> MediaAsset | None:
        """中文：处理“获取·owned”相关操作。
        English: Handles the get owned operation.
        """
        with self.session_factory() as db:
            return db.scalar(select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.media_type == "image",
            ))

    def mark_processing(self, asset_id: str, owner_user_id: str, provider: str, model: str) -> MediaAsset | None:
        """中文：将当前用户的图片标记为正在识别并记录模型来源。
        English: Marks an owned image as processing and records its model provenance.
        """
        with self.session_factory.begin() as db:
            entity = db.scalar(select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.media_type == "image",
            ).with_for_update())
            if entity is None:
                return None
            entity.processing_status = "processing"
            entity.error_code = None
            entity.ocr_provider = provider
            entity.ocr_model = model
            db.flush()
            db.refresh(entity)
            return entity

    def mark_ready(
        self,
        asset_id: str,
        owner_user_id: str,
        *,
        extracted_text: str,
        formulas: list[str],
        confidence: float,
        provider: str,
        model: str,
        validation_status: str,
        validation_issues: list[dict],
    ) -> MediaAsset | None:
        """中文：持久化成功的 OCR 文本、公式、置信度和来源。
        English: Persists successful OCR text, formulas, confidence, and provenance.
        """
        with self.session_factory.begin() as db:
            entity = db.scalar(select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.media_type == "image",
            ).with_for_update())
            if entity is None:
                return None
            entity.processing_status = "ready"
            entity.ocr_original_text = extracted_text
            entity.extracted_text = extracted_text
            entity.recognized_formulas = formulas
            entity.ocr_confidence = confidence
            entity.ocr_provider = provider
            entity.ocr_model = model
            entity.formula_validation_status = validation_status
            entity.formula_validation_issues = validation_issues
            entity.student_confirmed_at = None
            entity.error_code = None
            db.flush()
            db.refresh(entity)
            return entity

    def confirm_ocr(
        self,
        asset_id: str,
        owner_user_id: str,
        *,
        text: str,
        formulas: list[str],
        validation_status: str,
        validation_issues: list[dict],
        confirmed_at: datetime,
    ) -> MediaAsset | None:
        """中文：保存学生修正内容和公式复检结果，并记录确认时间。
        English: Saves student corrections and formula revalidation results with confirmation time.
        """
        with self.session_factory.begin() as db:
            entity = db.scalar(select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.media_type == "image",
                MediaAsset.processing_status == "ready",
            ).with_for_update())
            if entity is None:
                return None
            entity.extracted_text = text
            entity.recognized_formulas = formulas
            entity.formula_validation_status = validation_status
            entity.formula_validation_issues = validation_issues
            entity.student_confirmed_at = confirmed_at
            db.flush()
            db.refresh(entity)
            return entity

    def mark_failed(self, asset_id: str, owner_user_id: str, error_code: str) -> MediaAsset | None:
        """中文：记录可安全返回给前端的 OCR 失败代码。
        English: Records an OCR failure code that is safe to expose to the client.
        """
        with self.session_factory.begin() as db:
            entity = db.scalar(select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.media_type == "image",
            ).with_for_update())
            if entity is None:
                return None
            entity.processing_status = "failed"
            entity.error_code = error_code[:64]
            db.flush()
            db.refresh(entity)
            return entity

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.engine.dispose()
