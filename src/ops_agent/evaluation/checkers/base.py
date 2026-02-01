"""Base Checker Interface.

도구별 검사기를 위한 추상 기본 클래스.

Reference: docs/evaluation-design.md - Step 2
"""

from abc import ABC, abstractmethod

from ops_agent.evaluation.models import CheckResult, ToolResult


class BaseChecker(ABC):
    """도구별 검사기를 위한 추상 기본 클래스.

    모든 검사기는 이 클래스를 상속받아 구현해야 합니다.

    Example:
        class CloudWatchChecker(BaseChecker):
            @property
            def name(self) -> str:
                return "cloudwatch_accuracy"

            def check(self, response, tool_results) -> CheckResult:
                # 검사 로직 구현
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """검사기 이름 (로깅 및 결과 식별용)."""
        pass

    @abstractmethod
    def check(
        self,
        response: str,
        tool_results: list[ToolResult],
    ) -> CheckResult:
        """도구 결과 대비 응답 평가.

        Args:
            response: LLM이 생성한 응답 텍스트
            tool_results: 에이전트 실행 중 캡처된 도구 결과 목록

        Returns:
            CheckResult: 검사 결과 (점수, 통과 여부, 발견된 문제)
        """
        pass

    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화 (비교용).

        공백 정리, 소문자 변환 등.
        """
        return " ".join(text.lower().split())
