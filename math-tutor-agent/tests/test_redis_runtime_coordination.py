import os
import unittest
from uuid import uuid4

from redis import Redis

from app.cache.base import RuntimeCoordinationUnavailable, SessionLockBusy
from app.cache.redis_runtime import RedisRuntimeCache
from app.core.config import settings
from app.domain.schemas import TutoringSession
from app.domain.tutoring import TutorAction, TutorReply
from app.harness.contracts import HarnessRunResult


RUN_REDIS_TESTS = os.getenv("RUN_REDIS_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_REDIS_TESTS, "set RUN_REDIS_INTEGRATION_TESTS=1 to run Redis integration tests")
class RedisRuntimeCoordinationTests(unittest.TestCase):
    """中文：使用真实 Redis 验证幂等结果和分布式会话锁。
    English: Uses real Redis to verify idempotency results and distributed session locks.
    """

    def setUp(self) -> None:
        """中文：为每个测试创建随机键前缀，避免污染运行数据。
        English: Creates a random key prefix per test to isolate runtime data.
        """
        self.client = Redis.from_url(
            os.getenv("REDIS_TEST_URL", settings.redis_url),
            decode_responses=True,
        )
        self.client.ping()
        self.prefix = f"math-tutor:test:{uuid4()}"
        self.cache = self._cache(lock_wait_seconds=0.05)

    def tearDown(self) -> None:
        """中文：删除随机前缀下的全部 Redis 测试键。
        English: Deletes every Redis test key under the random prefix.
        """
        keys = list(self.client.scan_iter(match=f"{self.prefix}:*"))
        if keys:
            self.client.delete(*keys)
        self.client.close()

    def test_idempotency_result_round_trip_and_ttl(self) -> None:
        """中文：相同会话和客户端轮次可以读回同一执行结果及 TTL。
        English: The same session and client turn can retrieve the same result with a TTL.
        """
        result = self._run_result()
        self.cache.set_run_result("session-1", "client-turn-1", result)

        loaded = self.cache.get_run_result("session-1", "client-turn-1")
        key = self.cache.keys.turn_result("session-1", "client-turn-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.run_id, result.run_id)
        self.assertGreater(self.client.ttl(key), 0)
        self.assertIsNone(self.cache.get_run_result("session-1", "another-turn"))

    def test_invalid_idempotency_payload_fails_closed_and_is_deleted(self) -> None:
        """中文：损坏的幂等结果在严格模式下中断执行并清理坏数据。
        English: A corrupt idempotency result fails closed and removes the bad payload.
        """
        key = self.cache.keys.turn_result("session-2", "client-turn-2")
        self.client.set(key, "not-json", ex=60)

        with self.assertRaises(RuntimeCoordinationUnavailable):
            self.cache.get_run_result("session-2", "client-turn-2")
        self.assertIsNone(self.client.get(key))

    def test_lock_blocks_competing_worker_then_releases(self) -> None:
        """中文：持锁期间拒绝第二工作进程，释放后可以重新获取。
        English: A competing worker is rejected while locked and can acquire after release.
        """
        competitor = self._cache(lock_wait_seconds=0.02)
        with self.cache.lock_session("session-3"):
            with self.assertRaises(SessionLockBusy):
                with competitor.lock_session("session-3"):
                    self.fail("competing lock should not be acquired")

        with competitor.lock_session("session-3"):
            self.assertTrue(True)

    def _cache(self, *, lock_wait_seconds: float) -> RedisRuntimeCache:
        """中文：创建共享 Redis、独立配置的运行时缓存实例。
        English: Creates a runtime cache using shared Redis with isolated configuration.
        """
        return RedisRuntimeCache(
            client=self.client,
            key_prefix=self.prefix,
            session_ttl_seconds=60,
            idempotency_ttl_seconds=120,
            lock_ttl_seconds=10,
            lock_wait_seconds=lock_wait_seconds,
            coordination_fail_closed=True,
        )

    @staticmethod
    def _run_result() -> HarnessRunResult:
        """中文：创建可序列化的最小 Harness 执行结果。
        English: Creates a minimal serializable Harness run result.
        """
        session = TutoringSession(
            student_user_id=str(uuid4()),
            question="解方程 x² - 5x + 6 = 0",
        )
        return HarnessRunResult(
            run_id=str(uuid4()),
            session=session,
            reply=TutorReply(
                action=TutorAction.CLARIFY,
                text="你准备先从哪一步开始？",
                confidence=0.9,
            ),
            trace=[],
            duration_ms=12,
        )


if __name__ == "__main__":
    unittest.main()
