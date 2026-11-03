from app.domain.llm import LLMModelCatalog, LLMModelView
from app.providers.llm import llm_registry


class LLMModelService:
    """中文：定义“llmmodel·服务”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel service class and encapsulates data and behavior for that responsibility.
    """
    def catalog(self) -> LLMModelCatalog:
        """中文：处理“catalog”相关操作。
        English: Handles the catalog operation.
        """
        models = [
            LLMModelView(**item.__dict__)
            for item in llm_registry.list_models()
        ]
        return LLMModelCatalog(
            models=models,
            default_model_id=llm_registry.default_model_id,
        )


llm_model_service = LLMModelService()
