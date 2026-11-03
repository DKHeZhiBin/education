from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import RequestLoggingMiddleware, configure_logging


configure_logging(settings)
logger = logging.getLogger(__name__)

from app.api.errors import (
    normalized_http_exception_handler,
    normalized_validation_exception_handler,
)

from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.admin_knowledge import router as admin_knowledge_router
from app.api.routes.admin_generation import router as admin_generation_router
from app.api.routes.admin_human_review import router as admin_human_review_router
from app.api.routes.admin_revalidation import router as admin_revalidation_router
from app.api.routes.tutoring import router as tutoring_router
from app.api.routes.llm_models import router as llm_models_router
from app.api.routes.curriculum import router as curriculum_router
from app.api.routes.admin_curriculum import router as admin_curriculum_router
from app.api.routes.thinking_methods import router as thinking_methods_router
from app.api.routes.admin_thinking_methods import router as admin_thinking_methods_router
from app.services.periodic_revalidation import periodic_revalidation_service
from app.services.human_review import human_review_service
from app.services.knowledge_admin import knowledge_admin_service
from app.services.tutoring import tutoring_service
from app.services.problem_images import problem_image_service
from app.services.reviews import review_service
from app.services.auth import auth_service
from app.services.curriculum_admin import curriculum_admin_service
from app.services.thinking_methods import thinking_method_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    """中文：处理“lifespan”相关操作。
    English: Handles the lifespan operation.
    """
    logger.info("Math Tutor API started", extra={"event": "application.started"})
    try:
        yield
    finally:
        periodic_revalidation_service.close()
        human_review_service.close()
        knowledge_admin_service.close()
        tutoring_service.close()
        problem_image_service.close()
        review_service.close()
        auth_service.close()
        curriculum_admin_service.close()
        thinking_method_service.close()
        logger.info("Math Tutor API stopped", extra={"event": "application.stopped"})

app = FastAPI(
    title="Math Tutor Agent",
    version="0.1.0",
    description="A modular API for guided math tutoring.",
    lifespan=lifespan,
)

app.add_exception_handler(
    StarletteHTTPException,
    normalized_http_exception_handler,
)
app.add_exception_handler(
    RequestValidationError,
    normalized_validation_exception_handler,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware, config=settings)

app.include_router(health_router, prefix="/v1")
app.include_router(auth_router, prefix="/v1")
app.include_router(admin_knowledge_router, prefix="/v1")
app.include_router(admin_generation_router, prefix="/v1")
app.include_router(admin_human_review_router, prefix="/v1")
app.include_router(admin_revalidation_router, prefix="/v1")
app.include_router(tutoring_router, prefix="/v1")
app.include_router(llm_models_router, prefix="/v1")
app.include_router(curriculum_router, prefix="/v1")
app.include_router(admin_curriculum_router, prefix="/v1")
app.include_router(thinking_methods_router, prefix="/v1")
app.include_router(admin_thinking_methods_router, prefix="/v1")
