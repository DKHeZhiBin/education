from app.agents.tutoring_team import TeachingOrchestrator
from app.cache.factory import build_runtime_cache
from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.harness.contracts import HarnessBudget
from app.harness.math_tutor import MathTutorAgentHarness
from app.repositories.mysql_sessions import MySQLSessionRepository
from app.providers.knowledge import knowledge_retriever
from app.providers.student_history import MySQLStudentHistoryRetriever
from app.services.content_integrity import content_integrity_service
from app.agents.similar_practice import ConstrainedSimilarPracticeAgent
from app.repositories.practice_scope import PracticeScopeRepository


def build_math_tutor_harness() -> MathTutorAgentHarness:
    """中文：处理“构建·math·tutor·harness”相关操作。
    English: Handles the build math tutor harness operation.
    """
    engine = create_mysql_engine()
    session_factory = create_session_factory(engine)
    student_history_retriever = MySQLStudentHistoryRetriever(session_factory)
    return MathTutorAgentHarness(
        repository=MySQLSessionRepository(
            engine=engine,
            session_factory=session_factory,
        ),
        orchestrator=TeachingOrchestrator(
            max_revision_attempts=settings.solution_max_revision_attempts,
            knowledge_retriever=knowledge_retriever,
            student_history_retriever=student_history_retriever,
        ),
        budget=HarnessBudget(
            max_agent_calls=settings.harness_max_agent_calls,
            max_duration_ms=settings.harness_max_duration_ms,
        ),
        runtime_cache=build_runtime_cache(),
        content_integrity=content_integrity_service,
        practice_agent=ConstrainedSimilarPracticeAgent(
            PracticeScopeRepository(session_factory, student_history_retriever)
        ),
    )
