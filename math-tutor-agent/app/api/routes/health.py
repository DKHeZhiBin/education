from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.readiness import readiness_service

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process-only probe. It never calls an external dependency."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """Dependency probe used to decide whether this instance should receive traffic."""
    ready, payload = await readiness_service.check()
    return JSONResponse(status_code=200 if ready else 503, content=payload)
