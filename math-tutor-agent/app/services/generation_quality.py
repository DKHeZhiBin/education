from app.core.config import Settings, settings
from app.domain.generation_quality import (
    GenerationQualityReport,
    GenerationQualityScope,
    ProductionReleaseGate,
)
from app.repositories.generation_quality import GenerationQualityRepository


class GenerationQualityService:
    def __init__(
        self,
        repository: GenerationQualityRepository,
        config: Settings = settings,
    ) -> None:
        self.repository = repository
        self.config = config

    def report(self, scope: GenerationQualityScope) -> GenerationQualityReport:
        return self.repository.report(scope)

    def release_gate(self, scope: GenerationQualityScope) -> ProductionReleaseGate:
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
