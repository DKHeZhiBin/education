from app.agents.tutoring_team import TeachingOrchestrator
from app.cache.factory import build_runtime_cache
from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.harness.contracts import HarnessBudget
from app.harness.math_tutor import MathTutorAgentHarness
from app.repositories.mysql_sessions import MySQLSessionRepository
from app.providers.knowledge import knowledge_retriever
from app.services.content_integrity import content_integrity_service


def build_math_tutor_harness() -> MathTutorAgentHarness:
    engine = create_mysql_engine()
    return MathTutorAgentHarness(
        repository=MySQLSessionRepository(
            engine=engine,
            session_factory=create_session_factory(engine),
        ),
        orchestrator=TeachingOrchestrator(
            max_revision_attempts=settings.solution_max_revision_attempts,
            knowledge_retriever=knowledge_retriever,
        ),
        budget=HarnessBudget(
            max_agent_calls=settings.harness_max_agent_calls,
            max_duration_ms=settings.harness_max_duration_ms,
        ),
        runtime_cache=build_runtime_cache(),
        content_integrity=content_integrity_service,
    )
