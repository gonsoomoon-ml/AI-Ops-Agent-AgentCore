"""Evaluation Data Models.

평가 시스템에서 사용하는 데이터 모델 정의.

Reference: docs/evaluation-design.md - Step 1
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolType(Enum):
    """도구 유형."""

    CLOUDWATCH = "cloudwatch"
    DATADOG = "datadog"
    KNOWLEDGE_BASE = "knowledge_base"


class EvalVerdict(Enum):
    """평가 판정 결과.

    - PASS: 응답 품질 충족, 사용자에게 반환
    - REGENERATE: 품질 미달, 피드백과 함께 재생성
    - BLOCK: 심각한 문제, 경고와 함께 반환
    """

    PASS = "pass"
    REGENERATE = "regenerate"
    BLOCK = "block"


@dataclass
class ToolResult:
    """캡처된 도구 실행 결과.

    에이전트 실행 중 호출된 도구의 입력/출력을 저장.

    Attributes:
        tool_type: 도구 유형 (CloudWatch, Datadog, KB)
        tool_name: 도구 함수 이름
        tool_input: 도구 호출 시 전달된 입력
        tool_output: 도구 실행 결과 (파싱된 JSON)
    """

    tool_type: ToolType
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any]


@dataclass
class CheckResult:
    """단일 검사기의 결과.

    각 검사기(CloudWatch, Datadog 등)가 반환하는 개별 결과.

    Attributes:
        checker_name: 검사기 이름 (로깅용)
        score: 점수 (0.0 - 1.0)
        passed: 통과 여부
        issues: 발견된 문제 목록
        details: 상세 정보 (디버깅용)
    """

    checker_name: str
    score: float
    passed: bool
    issues: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """최종 평가 결과.

    모든 검사기 결과를 종합한 최종 판정.

    Attributes:
        verdict: 최종 판정 (PASS, REGENERATE, BLOCK)
        overall_score: 종합 점수 (0.0 - 1.0)
        check_results: 개별 검사기 결과 목록
        feedback: 재생성 시 제공할 피드백 (REGENERATE일 때만)
    """

    verdict: EvalVerdict
    overall_score: float
    check_results: list[CheckResult]
    feedback: str | None = None
