"""CloudWatch Checker.

CloudWatch 도구 결과 대비 응답의 사실 정확성 검사.

Reference: docs/evaluation-design.md - Step 3

검사 항목:
    1. 이벤트 수 정확성 (event_count)
    2. 에러 메시지 인용 여부
    3. 서비스/로그 그룹 언급 여부
    4. 메트릭 값 정확성 (해당 시)
"""

import re

from ops_agent.evaluation.checkers.base import BaseChecker
from ops_agent.evaluation.models import CheckResult, ToolResult, ToolType


class CloudWatchChecker(BaseChecker):
    """CloudWatch 데이터의 사실 정확성 검사기.

    응답이 CloudWatch 도구 결과를 정확하게 인용하는지 검사합니다.

    검사 항목:
        - 이벤트 수가 정확하게 언급되었는가?
        - 에러 메시지가 올바르게 인용되었는가?
        - 서비스/로그 그룹이 언급되었는가?
    """

    # 통과 임계값
    PASS_THRESHOLD = 0.7

    # 이벤트 수 매칭 패턴 (한글/영어)
    COUNT_PATTERNS = [
        r"(\d+)\s*건",
        r"(\d+)\s*개",
        r"(\d+)\s*(errors?|에러)",
        r"총\s*(\d+)",
        r"(\d+)\s*(events?|이벤트)",
        r"\*\*(\d+)건\*\*",
        r"\*\*(\d+)개\*\*",
    ]

    @property
    def name(self) -> str:
        """검사기 이름."""
        return "cloudwatch_accuracy"

    def check(
        self,
        response: str,
        tool_results: list[ToolResult],
    ) -> CheckResult:
        """CloudWatch 도구 결과 대비 응답 정확성 검사.

        Args:
            response: LLM 응답 텍스트
            tool_results: 캡처된 도구 결과 목록

        Returns:
            CheckResult: 검사 결과
        """
        # CloudWatch 결과만 필터링
        cw_results = [
            r for r in tool_results
            if r.tool_type == ToolType.CLOUDWATCH
        ]

        # CloudWatch 결과 없으면 스킵
        if not cw_results:
            return CheckResult(
                checker_name=self.name,
                score=1.0,
                passed=True,
                issues=[],
                details={"skipped": "no_cloudwatch_results"},
            )

        issues: list[str] = []
        total_checks = 0
        passed_checks = 0

        for result in cw_results:
            output = result.tool_output

            # 검사 1: 이벤트 수 정확성
            if "event_count" in output:
                total_checks += 1
                expected_count = output["event_count"]
                if self._verify_count_mentioned(response, expected_count):
                    passed_checks += 1
                else:
                    issues.append(
                        f"이벤트 수 불일치: 도구 반환 {expected_count}건, "
                        f"응답에서 확인 불가"
                    )

            # 검사 2: 에러 메시지 인용 여부
            if "events" in output and output["events"]:
                events = output["events"]
                cited_count = 0

                for event in events:
                    total_checks += 1
                    message = event.get("message", "")
                    key_phrases = self._extract_key_phrases(message)

                    if self._any_phrase_in_response(key_phrases, response):
                        passed_checks += 1
                        cited_count += 1
                    else:
                        # 첫 50자만 표시
                        short_msg = message[:50] + "..." if len(message) > 50 else message
                        issues.append(f"에러 미인용: {short_msg}")

            # 검사 3: 서비스/로그 그룹 언급 여부
            if "log_group" in output:
                total_checks += 1
                log_group = output["log_group"]
                service_name = self._extract_service_name(log_group)

                if service_name and service_name.lower() in response.lower():
                    passed_checks += 1
                else:
                    issues.append(f"서비스 미언급: {service_name}")

        # 점수 계산
        score = passed_checks / total_checks if total_checks > 0 else 1.0

        return CheckResult(
            checker_name=self.name,
            score=score,
            passed=score >= self.PASS_THRESHOLD,
            issues=issues,
            details={
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "cw_results_count": len(cw_results),
            },
        )

    def _verify_count_mentioned(self, response: str, expected: int) -> bool:
        """응답에 이벤트 수가 정확하게 언급되었는지 확인.

        Args:
            response: 응답 텍스트
            expected: 예상 이벤트 수

        Returns:
            bool: 정확한 수가 언급되었으면 True
        """
        for pattern in self.COUNT_PATTERNS:
            matches = re.findall(pattern, response, re.IGNORECASE)
            for match in matches:
                # 튜플이면 첫 번째 요소 (숫자 그룹)
                num_str = match[0] if isinstance(match, tuple) else match
                try:
                    if int(num_str) == expected:
                        return True
                except ValueError:
                    continue

        return False

    def _extract_key_phrases(self, message: str) -> list[str]:
        """로그 메시지에서 핵심 키워드 추출.

        Args:
            message: 로그 메시지

        Returns:
            list[str]: 핵심 키워드 목록
        """
        phrases = []

        # [ERROR] 500 - 형식에서 에러 내용 추출
        error_match = re.search(
            r'\[ERROR\]\s*\d*\s*[-:]?\s*(.+?)(?:[-:]|$)',
            message,
        )
        if error_match:
            error_text = error_match.group(1).strip()
            # 콜론으로 분리된 첫 부분
            parts = error_text.split(":")
            if parts:
                phrases.append(parts[0].strip())

        # 일반적인 에러 키워드 추출
        keywords = [
            "timeout",
            "connection",
            "failed",
            "error",
            "exception",
            "refused",
            "exhausted",
            "Redis",
            "Database",
            "payment",
            "gateway",
        ]

        message_lower = message.lower()
        for keyword in keywords:
            if keyword.lower() in message_lower:
                phrases.append(keyword)

        return phrases

    def _any_phrase_in_response(
        self,
        phrases: list[str],
        response: str,
    ) -> bool:
        """키워드 중 하나라도 응답에 있는지 확인.

        Args:
            phrases: 검색할 키워드 목록
            response: 응답 텍스트

        Returns:
            bool: 하나라도 발견되면 True
        """
        response_lower = response.lower()
        return any(
            phrase.lower() in response_lower
            for phrase in phrases
            if phrase  # 빈 문자열 제외
        )

    def _extract_service_name(self, log_group: str) -> str | None:
        """로그 그룹에서 서비스 이름 추출.

        Args:
            log_group: CloudWatch 로그 그룹 경로
                예: /aws/lambda/payment-service

        Returns:
            str | None: 서비스 이름 또는 None
        """
        if not log_group:
            return None

        # /로 분리하여 마지막 부분 추출
        parts = log_group.strip("/").split("/")
        return parts[-1] if parts else None
