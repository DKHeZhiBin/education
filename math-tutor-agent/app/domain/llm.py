from pydantic import BaseModel, Field


class LLMModelView(BaseModel):
    """中文：定义“llmmodel·view”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel view class and encapsulates data and behavior for that responsibility.
    """
    id: str = Field(min_length=3, max_length=180)
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=180)
    available: bool
    is_default: bool


class LLMModelCatalog(BaseModel):
    """中文：定义“llmmodel·catalog”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel catalog class and encapsulates data and behavior for that responsibility.
    """
    models: list[LLMModelView]
    default_model_id: str | None = None
