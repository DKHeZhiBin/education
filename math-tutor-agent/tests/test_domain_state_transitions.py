import unittest

from app.domain.generation import GenerationBatchStatus
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import (
    InvalidProblemTransition,
    ProblemContentStateMachine,
    ProblemTransitionRequest,
)
from app.domain.question_generation import GenerationBatchStateMachine


class ProblemContentStateMachineTests(unittest.TestCase):
    """中文：验证题目内容生命周期的允许路径和强制约束。
    English: Verifies allowed paths and mandatory constraints in the problem lifecycle.
    """

    def setUp(self) -> None:
        """中文：为每个测试创建无共享状态的状态机。
        English: Creates a stateless state machine for each test.
        """
        self.machine = ProblemContentStateMachine()

    def test_candidate_can_enter_validation(self) -> None:
        """中文：候选题可以进入验证状态。
        English: A candidate problem can enter validation.
        """
        result = self.machine.transition(self._request(
            ProblemContentStatus.CANDIDATE,
            ProblemContentStatus.VALIDATING,
        ))
        self.assertTrue(result.changed)
        self.assertEqual(result.current_status, ProblemContentStatus.VALIDATING)
        self.assertEqual(result.revision_attempts, 0)

    def test_same_status_is_idempotent_noop(self) -> None:
        """中文：重复提交相同状态不会产生新的迁移。
        English: Repeating the same state produces an idempotent no-op.
        """
        result = self.machine.transition(self._request(
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.VALIDATING,
        ))
        self.assertFalse(result.changed)
        self.assertEqual(result.checked_requirements, ["idempotent_noop"])

    def test_disallowed_transition_is_rejected(self) -> None:
        """中文：候选题不能绕过验证直接批准。
        English: A candidate cannot bypass validation and become approved directly.
        """
        with self.assertRaises(InvalidProblemTransition) as raised:
            self.machine.transition(self._request(
                ProblemContentStatus.CANDIDATE,
                ProblemContentStatus.APPROVED,
            ))
        self.assertEqual(raised.exception.code, "transition_not_allowed")

    def test_revision_requires_reason_and_increments_attempt(self) -> None:
        """中文：进入修订必须给出原因并消耗一次修订机会。
        English: Entering revision requires a reason and consumes one revision attempt.
        """
        with self.assertRaises(InvalidProblemTransition) as raised:
            self.machine.transition(self._request(
                ProblemContentStatus.VALIDATING,
                ProblemContentStatus.REVISION_REQUIRED,
            ))
        self.assertEqual(raised.exception.code, "status_reason_required")

        result = self.machine.transition(self._request(
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.REVISION_REQUIRED,
            reason="根数量验证失败",
            revision_attempts=1,
        ))
        self.assertEqual(result.revision_attempts, 2)
        self.assertEqual(result.status_reason, "根数量验证失败")

    def test_revision_limit_suggests_quarantine(self) -> None:
        """中文：两次修订耗尽后必须转入隔离建议。
        English: Exhausting two revisions produces a quarantine recommendation.
        """
        with self.assertRaises(InvalidProblemTransition) as raised:
            self.machine.transition(self._request(
                ProblemContentStatus.VALIDATING,
                ProblemContentStatus.REVISION_REQUIRED,
                reason="仍然验证失败",
                revision_attempts=2,
            ))
        self.assertEqual(raised.exception.code, "revision_limit_exhausted")
        self.assertEqual(
            raised.exception.suggested_status,
            ProblemContentStatus.QUARANTINED,
        )

    def test_retired_content_is_terminal(self) -> None:
        """中文：退役题目不能重新进入生产生命周期。
        English: Retired content cannot re-enter the production lifecycle.
        """
        with self.assertRaises(InvalidProblemTransition) as raised:
            self.machine.transition(self._request(
                ProblemContentStatus.RETIRED,
                ProblemContentStatus.VALIDATING,
            ))
        self.assertEqual(raised.exception.code, "transition_not_allowed")

    @staticmethod
    def _request(
        current: ProblemContentStatus,
        target: ProblemContentStatus,
        *,
        reason: str | None = None,
        revision_attempts: int = 0,
    ) -> ProblemTransitionRequest:
        """中文：创建只包含当前场景所需字段的迁移请求。
        English: Builds a transition request with only fields required by the scenario.
        """
        return ProblemTransitionRequest(
            problem_id="problem-test",
            generation_batch_id="batch-test" if target == ProblemContentStatus.APPROVED else None,
            current_status=current,
            target_status=target,
            reason=reason,
            revision_attempts=revision_attempts,
        )


class GenerationBatchStateMachineTests(unittest.TestCase):
    """中文：验证生成批次的暂停、恢复、取消和终态规则。
    English: Verifies pause, resume, cancel, and terminal rules for generation batches.
    """

    def test_running_batch_can_pause_and_resume(self) -> None:
        """中文：运行中的批次可以暂停，暂停后可以恢复。
        English: A running batch can pause and later resume.
        """
        paused = GenerationBatchStateMachine.transition(
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.PAUSED,
        )
        resumed = GenerationBatchStateMachine.transition(
            paused,
            GenerationBatchStatus.RUNNING,
        )
        self.assertEqual(resumed, GenerationBatchStatus.RUNNING)

    def test_terminal_batch_cannot_restart(self) -> None:
        """中文：完成批次不能重新进入运行状态。
        English: A completed batch cannot return to running.
        """
        with self.assertRaises(ValueError):
            GenerationBatchStateMachine.transition(
                GenerationBatchStatus.COMPLETED,
                GenerationBatchStatus.RUNNING,
            )

    def test_same_batch_status_is_idempotent(self) -> None:
        """中文：重复批次状态迁移保持幂等。
        English: Repeating a batch status transition is idempotent.
        """
        current = GenerationBatchStateMachine.transition(
            GenerationBatchStatus.PAUSED,
            GenerationBatchStatus.PAUSED,
        )
        self.assertEqual(current, GenerationBatchStatus.PAUSED)


if __name__ == "__main__":
    unittest.main()
