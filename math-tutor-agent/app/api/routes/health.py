from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.readiness import readiness_service

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """中文：处理“liveness”相关操作。
    English: Handles the liveness operation.

    原有说明 / Existing notes:
    Process-only probe. It never calls an external dependency.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """中文：处理“就绪状态”相关操作。
    English: Handles the readiness operation.

    原有说明 / Existing notes:
    Dependency probe used to decide whether this instance should receive traffic.
    """
    ready, payload = await readiness_service.check()
    return JSONResponse(status_code=200 if ready else 503, content=payload)
