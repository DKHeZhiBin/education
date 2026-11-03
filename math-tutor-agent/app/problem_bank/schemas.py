from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, model_validator


class TrustedSeedSource(BaseModel):
    """中文：定义“trusted·seed·source”类，封装该职责相关的数据与行为。
    English: Defines the trusted seed source class and encapsulates data and behavior for that responsibility.
    """
    registry_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=255)
    edition: str = Field(min_length=1, max_length=100)
    canonical_url: HttpUrl
    content_url: HttpUrl
    license_name: str = Field(min_length=1, max_length=100)
    license_url: HttpUrl
    license_evidence_url: HttpUrl
    attribution: str = Field(min_length=1, max_length=1000)
    accessed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class TrustedMotherProblemSeed(BaseModel):
    """中文：定义“trusted·mother·题目·seed”类，封装该职责相关的数据与行为。
    English: Defines the trusted mother problem seed class and encapsulates data and behavior for that responsibility.
    """
    external_id: str = Field(min_length=1, max_length=255)
    source_locator: str = Field(min_length=1, max_length=255)
    original_statement: str = Field(min_length=1, max_length=2000)
    statement_zh: str = Field(min_length=1, max_length=2000)
    equation: str = Field(min_length=3, max_length=500)
    standard_form: str = Field(min_length=3, max_length=500)
    variable: str = Field(min_length=1, max_length=32)
    expected_real_solutions: list[str]
    method: str = Field(pattern=r"^(quadratic_formula|direct_square_root|factoring)$")
    difficulty: int = Field(ge=1, le=5)
    knowledge_point_codes: list[str] = Field(min_length=1)


class TrustedMotherProblemDataset(BaseModel):
    """中文：定义“trusted·mother·题目·dataset”类，封装该职责相关的数据与行为。
    English: Defines the trusted mother problem dataset class and encapsulates data and behavior for that responsibility.
    """
    schema_version: str = "1.0"
    dataset_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    batch_key: str = Field(min_length=1, max_length=100)
    topic_code: str = Field(min_length=1, max_length=80)
    source: TrustedSeedSource
    verifier_key: str = Field(min_length=1, max_length=100)
    verifier_version: str = Field(min_length=1, max_length=32)
    problems: list[TrustedMotherProblemSeed] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_problems(self) -> TrustedMotherProblemDataset:
        """中文：处理“验证·unique·problems”相关操作。
        English: Handles the validate unique problems operation.
        """
        external_ids = [problem.external_id for problem in self.problems]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("trusted mother problem external ids must be unique")
        equations = [problem.equation for problem in self.problems]
        if len(equations) != len(set(equations)):
            raise ValueError("trusted mother problem equations must be unique")
        return self
