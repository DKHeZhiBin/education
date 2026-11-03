from app.core.config import Settings, settings
from app.domain.generation_quality import (
    GenerationQualityReport,
    GenerationQualityScope,
    ProductionReleaseGate,
)
from app.repositories.generation_quality import GenerationQualityRepository


class GenerationQualityService:
    """中文：定义“生成·质量·服务”类，封装该职责相关的数据与行为。
    English: Defines the generation quality service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(
        self,
        repository: GenerationQualityRepository,
        config: Settings = settings,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository
        self.config = config

    def report(self, scope: GenerationQualityScope) -> GenerationQualityReport:
        """中文：处理“报告”相关操作。
        English: Handles the report operation.
        """
        return self.repository.report(scope)

    def release_gate(self, scope: GenerationQualityScope) -> ProductionReleaseGate:
        """中文：处理“release·准入门”相关操作。
        English: Handles the release gate operation.
        """
        report = self.report(scope)
        metric = next(
            item for item in report.metrics
            if item.key == "erroneous_admission_rate"
        )
        minimum = self.config.quality_release_min_auto_admissions
        maximum = self.config.quality_max_erroneous_admission_rate
        if metric.denominator < minimum:
            status = "blocked"
            reason = "insufficient_samples"
        elif metric.rate is not None and metric.rate > maximum:
            status = "blocked"
            reason = "threshold_exceeded"
        else:
            status = "passed"
            reason = "within_threshold"
        return ProductionReleaseGate(
            status=status,
            reason=reason,
            maximum_erroneous_admission_rate=maximum,
            minimum_auto_admissions=minimum,
            auto_admission_count=metric.denominator,
            erroneous_admission_count=metric.numerator,
            erroneous_admission_rate=metric.rate,
            report=report,
        )


generation_quality_service = GenerationQualityService(GenerationQualityRepository())
