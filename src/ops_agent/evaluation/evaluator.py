"""OpsAgent Evaluator.

응답 품질 평가 메인 오케스트레이터.

Reference: docs/evaluation-design.md - Step 4

사용법:
    evaluator = OpsAgentEvaluator()
    result = evaluator.evaluate(response, tool_results)

    if result.verdict == EvalVerdict.PASS:
        return response
    elif result.verdict == EvalVerdict.REGENERATE:
        # 피드백과 함께 재생성
        ...
"""

import logging

from ops_agent.evaluation.checkers.base import BaseChecker
from ops_agent.evaluation.checkers.cloudwatch import CloudWatchChecker
from ops_agent.evaluation.models import (
    CheckResult,
    EvalResult,
    EvalVerdict,
    ToolResult,
)

logger = logging.getLogger(__name__)


class OpsAgentEvaluator:
    """응답 품질 평가 메인 오케스트레이터.

    여러 검사기를 실행하고 결과를 종합하여 최종 판정을 내립니다.

    Attributes:
        pass_threshold: 통과 임계값 (기본: 0.7)
        block_threshold: 차단 임계값 (기본: 0.3)
        checkers: 등록된 검사기 목록

    Example:
        evaluator = OpsAgentEvaluator(pass_threshold=0.7)
        result = evaluator.evaluate(response, tool_results)

        if result.verdict == EvalVerdict.PASS:
            return response
        elif result.verdict == EvalVerdict.REGENERATE:
            retry_with_feedback(result.feedback)
    """

    def __init__(
        self,
        pass_threshold: float = 0.7,
        block_threshold: float = 0.3,
    ) -> None:
        """평가기 초기화.

        Args:
            pass_threshold: 통과 임계값 (0.0 - 1.0)
            block_threshold: 차단 임계값 (이 미만이면 BLOCK)
        """
        self.pass_threshold = pass_threshold
        self.block_threshold = block_threshold

        # 검사기 등록
        self.checkers: list[BaseChecker] = [
            CloudWatchChecker(),
            # DatadogChecker(),       # Phase 2
            # KnowledgeBaseChecker(), # Phase 3
        ]

        logger.debug(
            f"[Evaluator] 초기화: pass={pass_threshold}, "
            f"block={block_threshold}, checkers={len(self.checkers)}"
        )

    def evaluate(
        self,
        response: str,
        tool_results: list[ToolResult],
    ) -> EvalResult:
        """응답 품질 평가.

        모든 검사기를 실행하고 결과를 종합합니다.

        Args:
            response: LLM이 생성한 응답 텍스트
            tool_results: 에이전트 실행 중 캡처된 도구 결과 목록

        Returns:
            EvalResult: 최종 평가 결과
        """
        check_results: list[CheckResult] = []

        # 모든 검사기 실행
        for checker in self.checkers:
            try:
                result = checker.check(response, tool_results)
                check_results.append(result)
                logger.debug(
                    f"[Evaluator] {checker.name}: "
                    f"score={result.score:.2f}, passed={result.passed}"
                )
            except Exception as e:
                logger.error(f"[Evaluator] {checker.name} 오류: {e}")
                # 오류 시 중립 결과
                check_results.append(CheckResult(
                    checker_name=checker.name,
                    score=0.5,
                    passed=True,
                    issues=[f"검사 오류: {e}"],
                    details={"error": str(e)},
                ))

        # 전체 점수 계산
        overall_score = self._calculate_overall_score(check_results)

        # 판정 결정
        verdict = self._determine_verdict(overall_score, check_results)

        # 재생성 필요 시 피드백 생성
        feedback = None
        if verdict == EvalVerdict.REGENERATE:
            feedback = self._generate_feedback(check_results)

        logger.info(
            f"[Evaluator] 결과: score={overall_score:.2f}, "
            f"verdict={verdict.value}"
        )

        return EvalResult(
            verdict=verdict,
            overall_score=overall_score,
            check_results=check_results,
            feedback=feedback,
        )

    def _calculate_overall_score(
        self,
        check_results: list[CheckResult],
    ) -> float:
        """전체 점수 계산 (가중 평균).

        Args:
            check_results: 개별 검사 결과 목록

        Returns:
            float: 전체 점수 (0.0 - 1.0)
        """
        if not check_results:
            return 1.0

        # 현재는 단순 평균, 향후 가중치 적용 가능
        # weights = {"cloudwatch_accuracy": 0.4, "datadog_accuracy": 0.4, ...}
        total = sum(r.score for r in check_results)
        return total / len(check_results)

    def _determine_verdict(
        self,
        score: float,
        check_results: list[CheckResult],
    ) -> EvalVerdict:
        """최종 판정 결정.

        Args:
            score: 전체 점수
            check_results: 개별 검사 결과 목록

        Returns:
            EvalVerdict: PASS, REGENERATE, 또는 BLOCK
        """
        # 심각한 실패 (점수 < 0.3) 있으면 BLOCK
        if any(r.score < self.block_threshold for r in check_results):
            return EvalVerdict.BLOCK

        # 임계값 이상이면 PASS
        if score >= self.pass_threshold:
            return EvalVerdict.PASS

        # 그 외 REGENERATE
        return EvalVerdict.REGENERATE

    def _generate_feedback(
        self,
        check_results: list[CheckResult],
    ) -> str:
        """재생성용 피드백 생성.

        실패한 검사 항목의 문제점을 정리하여 피드백을 생성합니다.

        Args:
            check_results: 개별 검사 결과 목록

        Returns:
            str: 재생성 시 사용할 피드백 텍스트
        """
        failed_checks = [r for r in check_results if not r.passed]

        if not failed_checks:
            return "응답 품질을 개선해주세요."

        feedback_parts = ["이전 응답의 문제점:"]

        for check in failed_checks:
            feedback_parts.append(f"\n[{check.checker_name}] (점수: {check.score:.1%})")
            # 이슈 최대 3개만 포함
            for issue in check.issues[:3]:
                feedback_parts.append(f"  - {issue}")

            if len(check.issues) > 3:
                feedback_parts.append(f"  - ... 외 {len(check.issues) - 3}건")

        feedback_parts.append("\n\n위 문제점을 수정하여 다시 답변해주세요.")
        feedback_parts.append("특히 도구 결과의 데이터를 정확하게 인용해주세요.")

        return "\n".join(feedback_parts)
