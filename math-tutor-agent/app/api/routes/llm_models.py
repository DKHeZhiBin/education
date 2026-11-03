from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUser
from app.domain.llm import LLMModelCatalog
from app.services.llm_models import llm_model_service


router = APIRouter(prefix="/llm", tags=["llm-models"])


@router.get("/models", response_model=LLMModelCatalog)
def list_llm_models(_: CurrentUser) -> LLMModelCatalog:
    """中文：处理“列出·llm·models”相关操作。
    English: Handles the list llm models operation.
    """
    return llm_model_service.catalog()
