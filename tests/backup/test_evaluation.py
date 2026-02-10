"""Evaluation Module Tests.

평가 시스템 단위 테스트.

실행 방법:
    uv run pytest tests/test_evaluation.py -v
    uv run pytest tests/test_evaluation.py -v -k "cloudwatch"
"""

import pytest

from ops_agent.evaluation import (
    CheckResult,
    EvalResult,
    EvalVerdict,
    OpsAgentEvaluator,
    ToolResult,
    ToolType,
)
from ops_agent.evaluation.checkers.cloudwatch import CloudWatchChecker


# ========== Fixtures ==========

@pytest.fixture
def cloudwatch_tool_result() -> ToolResult:
    """CloudWatch 도구 결과 샘플."""
    return ToolResult(
        tool_type=ToolType.CLOUDWATCH,
        tool_name="cloudwatch_filter_log_events",
        tool_input={
            "log_group_name": "/aws/lambda/payment-service",
            "filter_pattern": "?ERROR ?500",
            "time_range": "1h",
        },
        tool_output={
            "status": "success",
            "log_group": "/aws/lambda/payment-service",
            "filter_pattern": "?ERROR ?500",
            "time_range": "1h",
            "event_count": 4,
            "events": [
                {
                    "timestamp": "2026-01-31T03:00:00",
                    "message": "[ERROR] 500 Internal Server Error - Connection timeout to payment gateway",
                    "logStreamName": "payment-service/prod/i-0abc123",
                },
                {
                    "timestamp": "2026-01-31T03:03:00",
                    "message": "[ERROR] 500 Internal Server Error - Database connection pool exhausted",
                    "logStreamName": "payment-service/prod/i-0abc123",
                },
                {
                    "timestamp": "2026-01-31T03:07:00",
                    "message": "[ERROR] 500 Internal Server Error - Redis cache connection failed",
                    "logStreamName": "payment-service/prod/i-0def456",
                },
                {
                    "timestamp": "2026-01-31T03:12:00",
                    "message": "[ERROR] 500 Internal Server Error - Timeout waiting for response",
                    "logStreamName": "payment-service/prod/i-0def456",
                },
            ],
        },
    )


@pytest.fixture
def good_response() -> str:
    """좋은 응답 예시 (정확한 데이터 인용)."""
    return """## 조회 결과

최근 1시간 동안 payment-service에서 **4건의 에러**가 발생했습니다.

### 에러 상세

1. **03:00:00** - Connection timeout to payment gateway
2. **03:03:00** - Database connection pool exhausted
3. **03:07:00** - Redis cache connection failed
4. **03:12:00** - Timeout waiting for response

### 분석

주요 문제점:
- Payment gateway 연결 타임아웃
- 데이터베이스 커넥션 풀 고갈
- Redis 캐시 연결 실패

### 권장 조치

1. Payment gateway 상태 확인
2. 데이터베이스 커넥션 풀 설정 검토
3. Redis 클러스터 상태 점검
"""


@pytest.fixture
def bad_response_wrong_count() -> str:
    """나쁜 응답 예시 (잘못된 이벤트 수)."""
    return """## 조회 결과

최근 1시간 동안 payment-service에서 **10건의 에러**가 발생했습니다.

에러가 많이 발생하고 있습니다. 시스템을 점검하세요.
"""


@pytest.fixture
def bad_response_no_citation() -> str:
    """나쁜 응답 예시 (에러 내용 미인용)."""
    return """## 조회 결과

payment-service에서 4건의 에러가 발생했습니다.

일반적인 서버 오류입니다. 로그를 확인하고 모니터링을 강화하세요.
"""


# ========== CloudWatchChecker Tests ==========

class TestCloudWatchChecker:
    """CloudWatchChecker 테스트."""

    def test_check_good_response_passes(
        self,
        cloudwatch_tool_result: ToolResult,
        good_response: str,
    ):
        """좋은 응답은 검사를 통과해야 함."""
        checker = CloudWatchChecker()
        result = checker.check(good_response, [cloudwatch_tool_result])

        assert result.passed is True
        assert result.score >= 0.7
        assert len(result.issues) == 0 or result.score >= 0.7

    def test_check_wrong_count_fails(
        self,
        cloudwatch_tool_result: ToolResult,
        bad_response_wrong_count: str,
    ):
        """잘못된 이벤트 수는 검사 실패해야 함."""
        checker = CloudWatchChecker()
        result = checker.check(bad_response_wrong_count, [cloudwatch_tool_result])

        assert result.passed is False
        assert "이벤트 수 불일치" in str(result.issues)

    def test_check_no_citation_has_lower_score(
        self,
        cloudwatch_tool_result: ToolResult,
        bad_response_no_citation: str,
    ):
        """에러 내용 미인용 시 점수가 낮아야 함."""
        checker = CloudWatchChecker()
        result = checker.check(bad_response_no_citation, [cloudwatch_tool_result])

        # 4건 언급은 했으므로 완전 실패는 아님
        # 하지만 에러 내용 미인용으로 점수 감소
        assert result.score < 1.0

    def test_check_no_cloudwatch_results_skips(self):
        """CloudWatch 결과 없으면 스킵."""
        checker = CloudWatchChecker()

        # Datadog 결과만 있는 경우
        datadog_result = ToolResult(
            tool_type=ToolType.DATADOG,
            tool_name="datadog_get_metrics",
            tool_input={},
            tool_output={"metric": "cpu", "value": 85},
        )

        result = checker.check("any response", [datadog_result])

        assert result.passed is True
        assert result.score == 1.0
        assert result.details.get("skipped") == "no_cloudwatch_results"

    def test_verify_count_patterns(self):
        """이벤트 수 패턴 매칭 테스트."""
        checker = CloudWatchChecker()

        # 다양한 패턴 테스트
        test_cases = [
            ("4건의 에러가 발생했습니다.", 4, True),
            ("**4건**의 에러", 4, True),
            ("총 4개의 이벤트", 4, True),
            ("4 errors found", 4, True),
            ("10건의 에러", 4, False),  # 잘못된 수
            ("에러가 발생했습니다", 4, False),  # 수 미언급
        ]

        for text, expected, should_match in test_cases:
            result = checker._verify_count_mentioned(text, expected)
            assert result == should_match, f"Failed for: {text}"


# ========== OpsAgentEvaluator Tests ==========

class TestOpsAgentEvaluator:
    """OpsAgentEvaluator 테스트."""

    def test_evaluate_good_response_passes(
        self,
        cloudwatch_tool_result: ToolResult,
        good_response: str,
    ):
        """좋은 응답은 PASS 판정."""
        evaluator = OpsAgentEvaluator()
        result = evaluator.evaluate(good_response, [cloudwatch_tool_result])

        assert result.verdict == EvalVerdict.PASS
        assert result.overall_score >= 0.7
        assert result.feedback is None

    def test_evaluate_bad_response_regenerates(
        self,
        cloudwatch_tool_result: ToolResult,
        bad_response_wrong_count: str,
    ):
        """나쁜 응답은 REGENERATE 판정."""
        evaluator = OpsAgentEvaluator()
        result = evaluator.evaluate(bad_response_wrong_count, [cloudwatch_tool_result])

        assert result.verdict in [EvalVerdict.REGENERATE, EvalVerdict.BLOCK]
        if result.verdict == EvalVerdict.REGENERATE:
            assert result.feedback is not None
            assert "문제점" in result.feedback

    def test_evaluate_empty_tool_results_passes(self):
        """도구 결과 없으면 PASS."""
        evaluator = OpsAgentEvaluator()
        result = evaluator.evaluate("any response", [])

        assert result.verdict == EvalVerdict.PASS
        assert result.overall_score == 1.0

    def test_generate_feedback_includes_issues(
        self,
        cloudwatch_tool_result: ToolResult,
        bad_response_wrong_count: str,
    ):
        """피드백에 문제점이 포함되어야 함."""
        evaluator = OpsAgentEvaluator()
        result = evaluator.evaluate(bad_response_wrong_count, [cloudwatch_tool_result])

        if result.feedback:
            assert "이전 응답의 문제점" in result.feedback
            assert "cloudwatch" in result.feedback.lower()

    def test_custom_thresholds(self):
        """커스텀 임계값 테스트."""
        # 매우 엄격한 설정
        strict_evaluator = OpsAgentEvaluator(pass_threshold=0.95)

        # 매우 관대한 설정
        lenient_evaluator = OpsAgentEvaluator(pass_threshold=0.3)

        tool_result = ToolResult(
            tool_type=ToolType.CLOUDWATCH,
            tool_name="test",
            tool_input={},
            tool_output={"event_count": 2, "events": [], "log_group": "/test"},
        )

        response = "2건의 에러가 test에서 발생"

        strict_result = strict_evaluator.evaluate(response, [tool_result])
        lenient_result = lenient_evaluator.evaluate(response, [tool_result])

        # 같은 응답이라도 임계값에 따라 판정이 다를 수 있음
        assert lenient_result.verdict == EvalVerdict.PASS


# ========== Integration Tests ==========

class TestEvaluationIntegration:
    """통합 테스트."""

    def test_full_evaluation_flow(self, cloudwatch_tool_result: ToolResult):
        """전체 평가 흐름 테스트."""
        evaluator = OpsAgentEvaluator()

        # Step 1: 나쁜 응답 평가
        bad_response = "에러가 발생했습니다. 확인하세요."
        result1 = evaluator.evaluate(bad_response, [cloudwatch_tool_result])

        assert result1.verdict in [EvalVerdict.REGENERATE, EvalVerdict.BLOCK]

        # Step 2: 피드백 확인
        if result1.verdict == EvalVerdict.REGENERATE:
            assert result1.feedback is not None

        # Step 3: 개선된 응답 평가
        improved_response = """payment-service에서 4건의 에러가 발생했습니다.

주요 에러:
- Connection timeout to payment gateway
- Database connection pool exhausted
- Redis cache connection failed

권장 조치: Payment gateway 및 DB 연결 상태 점검"""

        result2 = evaluator.evaluate(improved_response, [cloudwatch_tool_result])

        # 개선된 응답은 더 높은 점수
        assert result2.overall_score > result1.overall_score


# ========== Edge Cases ==========

class TestEdgeCases:
    """엣지 케이스 테스트."""

    def test_empty_response(self, cloudwatch_tool_result: ToolResult):
        """빈 응답 처리."""
        checker = CloudWatchChecker()
        result = checker.check("", [cloudwatch_tool_result])

        assert result.passed is False
        assert result.score < 0.5

    def test_korean_english_mixed(self, cloudwatch_tool_result: ToolResult):
        """한영 혼용 응답 처리."""
        checker = CloudWatchChecker()

        mixed_response = """payment-service에서 4건의 error가 발생.
Connection timeout 및 Database 연결 문제 확인됨."""

        result = checker.check(mixed_response, [cloudwatch_tool_result])

        # 핵심 정보가 포함되어 있으면 통과
        assert result.score > 0.5

    def test_special_characters_in_message(self):
        """특수문자 포함 메시지 처리."""
        checker = CloudWatchChecker()

        tool_result = ToolResult(
            tool_type=ToolType.CLOUDWATCH,
            tool_name="test",
            tool_input={},
            tool_output={
                "event_count": 1,
                "log_group": "/aws/lambda/test",
                "events": [{
                    "message": "[ERROR] Failed: {\"code\": 500, \"msg\": \"error\"}",
                }],
            },
        )

        response = "1건의 에러: Failed 발생 (code 500)"
        result = checker.check(response, [tool_result])

        # 파싱 오류 없이 처리되어야 함
        assert isinstance(result, CheckResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
