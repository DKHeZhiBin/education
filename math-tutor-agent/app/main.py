from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.admin_knowledge import router as admin_knowledge_router
from app.api.routes.admin_generation import router as admin_generation_router
from app.api.routes.admin_revalidation import router as admin_revalidation_router
from app.api.routes.tutoring import router as tutoring_router
from app.services.periodic_revalidation import periodic_revalidation_service
from app.services.tutoring import tutoring_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    periodic_revalidation_service.close()
    tutoring_service.close()

app = FastAPI(
    title="Math Tutor Agent",
    version="0.1.0",
    description="A modular API for guided math tutoring.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/v1")
app.include_router(auth_router, prefix="/v1")
app.include_router(admin_knowledge_router, prefix="/v1")
app.include_router(admin_generation_router, prefix="/v1")
app.include_router(admin_revalidation_router, prefix="/v1")
app.include_router(tutoring_router, prefix="/v1")
