import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.api.errors import tutoring_error
from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.auth import AuthenticatedUser
from app.domain.problem_image import ConfirmProblemImageOCRRequest, ProblemImageUpload
from app.models import MediaAsset
from app.providers.ocr import OCRProvider, OCRProviderError, OCRRequest, ocr_provider
from app.providers.problem_image_storage import (
    InvalidProblemImage,
    ProblemImageTooLarge,
    problem_image_storage,
)
from app.repositories.problem_images import ProblemImageRepository
from app.services.auth import auth_service
from app.verifiers.formula_structure import formula_structure_checker


STATUS_MESSAGES = {
    "pending": "图片已上传，正在等待 OCR 识别。你也可以先手动输入题目文字。",
    "processing": "正在识别图片中的题目，请稍候。",
    "ready": "图片题目识别完成，请核对公式并确认。",
    "failed": "图片识别失败，请重新上传或手动输入题目。",
}

logger = logging.getLogger(__name__)


class ProblemImageService:
    """中文：定义“题目·图片·服务”类，封装该职责相关的数据与行为。
    English: Defines the problem image service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, provider: OCRProvider = ocr_provider) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        engine = create_mysql_engine()
        self.repository = ProblemImageRepository(engine, create_session_factory(engine))
        self.provider = provider

    async def upload(self, file: UploadFile, actor: AuthenticatedUser) -> ProblemImageUpload:
        """中文：处理“upload”相关操作。
        English: Handles the upload operation.
        """
        auth_service.require_role(actor, "student")
        asset_id = str(uuid4())
        original_filename = Path(file.filename or "problem-image").name[:255]
        try:
            stored = await problem_image_storage.save(file, actor.id, asset_id)
        except ProblemImageTooLarge as error:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=tutoring_error(
                    "problem_image_too_large",
                    f"图片不能超过 {settings.problem_image_max_bytes // (1024 * 1024)} MB。",
                ),
            ) from error
        except InvalidProblemImage as error:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=tutoring_error(
                    "unsupported_problem_image",
                    "仅支持真实的 JPEG、PNG 或 WebP 图片。",
                ),
            ) from error

        try:
            entity = self.repository.create(
                asset_id=asset_id,
                owner_user_id=actor.id,
                storage_key=stored.storage_key,
                original_filename=original_filename,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                content_sha256=stored.content_sha256,
                expires_at=self._now() + timedelta(days=settings.problem_image_retention_days),
            )
        except Exception:
            problem_image_storage.delete(stored.storage_key)
            raise
        return self._view(entity)

    async def recognize(self, asset_id: str, owner_user_id: str) -> None:
        """中文：在后台执行图片题目及公式识别，并推进处理状态。
        English: Recognizes problem text and formulas in the background and advances processing state.
        """
        entity = self.repository.get_owned(asset_id, owner_user_id)
        if entity is None or entity.processing_status not in {"pending", "failed"}:
            return
        if not self.provider.available:
            self.repository.mark_failed(asset_id, owner_user_id, "ocr_not_configured")
            return
        self.repository.mark_processing(
            asset_id,
            owner_user_id,
            self.provider.provider_id,
            self.provider.model_name,
        )
        try:
            content = problem_image_storage.read(entity.storage_key)
            result = await asyncio.to_thread(
                self.provider.recognize,
                OCRRequest(
                    content=content,
                    mime_type=entity.mime_type,
                    filename=entity.original_filename,
                ),
            )
            structure_check = formula_structure_checker.check(
                result.question_text,
                result.formulas_latex,
            )
            self.repository.mark_ready(
                asset_id,
                owner_user_id,
                extracted_text=result.question_text,
                formulas=list(structure_check.formulas),
                confidence=result.confidence,
                provider=result.provider_id,
                model=result.model_name,
                validation_status=structure_check.status,
                validation_issues=[issue.model_dump(mode="json") for issue in structure_check.issues],
            )
        except OCRProviderError as error:
            logger.warning(
                "Problem image OCR failed",
                extra={"asset_id": asset_id, "ocr_error_code": error.code},
            )
            self.repository.mark_failed(asset_id, owner_user_id, error.code)
        except FileNotFoundError:
            logger.warning("Problem image disappeared before OCR", extra={"asset_id": asset_id})
            self.repository.mark_failed(asset_id, owner_user_id, "ocr_source_missing")
        except Exception:
            logger.exception("Unexpected problem image OCR failure", extra={"asset_id": asset_id})
            self.repository.mark_failed(asset_id, owner_user_id, "ocr_internal_error")

    def get(self, asset_id: str, actor: AuthenticatedUser) -> ProblemImageUpload:
        """中文：处理“获取”相关操作。
        English: Handles the get operation.
        """
        auth_service.require_role(actor, "student")
        entity = self.repository.get_owned(asset_id, actor.id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "problem_image_not_found",
                    "题目图片不存在或已经过期。",
                ),
            )
        return self._view(entity)

    def confirm(
        self,
        asset_id: str,
        request: ConfirmProblemImageOCRRequest,
        actor: AuthenticatedUser,
    ) -> ProblemImageUpload:
        """中文：复检学生修正后的公式，并保存其明确确认。
        English: Revalidates student-corrected formulas and stores explicit confirmation.
        """
        auth_service.require_role(actor, "student")
        entity = self.repository.get_owned(asset_id, actor.id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error("problem_image_not_found", "题目图片不存在或已经过期。"),
            )
        if entity.processing_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=tutoring_error(
                    "problem_image_not_ready",
                    "图片尚未识别完成，暂时不能确认。",
                    retryable=True,
                ),
            )
        formulas = request.formulas_latex or list(formula_structure_checker.extract_formulas(request.text))
        structure_check = formula_structure_checker.check(request.text.strip(), formulas)
        if structure_check.status == "invalid":
            first_issue = next(issue for issue in structure_check.issues if issue.severity == "error")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=tutoring_error(
                    "invalid_formula_structure",
                    f"公式结构仍需修正：{first_issue.message}",
                ),
            )
        confirmed = self.repository.confirm_ocr(
            asset_id,
            actor.id,
            text=request.text.strip(),
            formulas=list(structure_check.formulas),
            validation_status=structure_check.status,
            validation_issues=[issue.model_dump(mode="json") for issue in structure_check.issues],
            confirmed_at=self._now(),
        )
        if confirmed is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=tutoring_error(
                    "problem_image_state_changed",
                    "图片状态已经变化，请刷新后重新确认。",
                    retryable=True,
                ),
            )
        return self._view(confirmed)

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.repository.close()

    @staticmethod
    def _view(entity: MediaAsset) -> ProblemImageUpload:
        """中文：处理“view”相关操作。
        English: Handles the view operation.
        """
        status_message = STATUS_MESSAGES.get(entity.processing_status, "图片状态已更新。")
        if entity.processing_status == "failed" and entity.error_code == "ocr_not_configured":
            status_message = "OCR 尚未配置，图片已保留；请先手动输入题目文字。"
        return ProblemImageUpload(
            id=entity.id,
            status=entity.processing_status,
            original_filename=entity.original_filename,
            mime_type=entity.mime_type,
            size_bytes=entity.size_bytes,
            extracted_text=entity.extracted_text,
            error_code=entity.error_code,
            ocr_provider=entity.ocr_provider,
            ocr_model=entity.ocr_model,
            ocr_confidence=entity.ocr_confidence,
            recognized_formulas=list(entity.recognized_formulas or []),
            formula_validation_status=entity.formula_validation_status,
            formula_validation_issues=list(entity.formula_validation_issues or []),
            student_confirmed_at=entity.student_confirmed_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            expires_at=entity.expires_at,
            status_message=status_message,
        )

    @staticmethod
    def _now() -> datetime:
        """中文：处理“now”相关操作。
        English: Handles the now operation.
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)


problem_image_service = ProblemImageService()
