"""Graph 유틸리티.

그래프 노드에서 사용하는 공통 유틸리티를 제공합니다.

Classes:
    Colors: 콘솔 출력용 컬러 코드
    StepPrinter: 노드 실행 단계 출력
    ToolResultExtractor: 도구 결과 추출

Functions:
    infer_tool_type: 출력 구조에서 도구 유형 추론
    build_retry_prompt: 재시도용 프롬프트 생성
"""

import json
from typing import Any

from ops_agent.evaluation.models import ToolResult, ToolType


# ==========================================================================
# 콘솔 컬러
# ==========================================================================
class Colors:
    """콘솔 출력용 컬러 코드."""

    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    END = "\033[0m"


# ==========================================================================
# 도구 유틸리티
# ==========================================================================
def infer_tool_type(output: dict) -> ToolType:
    """출력 구조에서 도구 유형 추론.

    Args:
        output: 도구 출력 딕셔너리

    Returns:
        추론된 ToolType
    """
    if any(key in output for key in ["log_group", "events", "filter_pattern"]):
        return ToolType.CLOUDWATCH
    if any(key in output for key in ["metric", "incidents", "monitors"]):
        return ToolType.DATADOG
    if any(key in output for key in ["kb_id", "documents", "sources", "chunks"]):
        return ToolType.KNOWLEDGE_BASE
    return ToolType.CLOUDWATCH


def build_retry_prompt(prompt: str, feedback: str) -> str:
    """재시도용 프롬프트 생성.

    Args:
        prompt: 원본 사용자 프롬프트
        feedback: 평가 피드백

    Returns:
        피드백이 포함된 재시도 프롬프트
    """
    return f"""이전 질문: {prompt}

{feedback}

위 피드백을 반영하여 다시 답변해주세요.
도구 결과의 데이터를 정확하게 인용하고, 구체적인 분석을 제공해주세요."""


# ==========================================================================
# 도구 결과 추출
# ==========================================================================
class ToolResultExtractor:
    """도구 결과 추출기.

    에이전트 메시지에서 도구 호출 결과를 추출합니다.

    Example:
        extractor = ToolResultExtractor()
        results = extractor.from_messages(agent.messages)
    """

    @staticmethod
    def from_messages(messages: list) -> list[ToolResult]:
        """메시지 목록에서 도구 결과 추출.

        Args:
            messages: 에이전트 메시지 목록

        Returns:
            추출된 ToolResult 목록
        """
        tool_results = []

        for msg in messages:
            if msg.get("role") != "user":
                continue

            for content in msg.get("content", []):
                if "toolResult" not in content:
                    continue

                tool_result = ToolResultExtractor._parse_tool_result(content["toolResult"])
                if tool_result:
                    tool_results.append(tool_result)

        return tool_results

    @staticmethod
    def _parse_tool_result(tool_result_data: dict) -> ToolResult | None:
        """단일 도구 결과 파싱.

        Args:
            tool_result_data: toolResult 딕셔너리

        Returns:
            ToolResult 또는 None
        """
        tool_use_id = tool_result_data.get("toolUseId", "")
        content_list = tool_result_data.get("content", [])

        # 텍스트 콘텐츠 추출
        text_content = ""
        for c in content_list:
            if "text" in c:
                text_content = c["text"]
                break

        # JSON 파싱
        try:
            output = json.loads(text_content) if text_content else {}
        except json.JSONDecodeError:
            output = {"raw": text_content}

        # 도구 유형 추론
        tool_type = infer_tool_type(output)

        return ToolResult(
            tool_type=tool_type,
            tool_name=tool_use_id,
            tool_input={},
            tool_output=output,
        )


# ==========================================================================
# 단계 출력
# ==========================================================================
class StepPrinter:
    """노드 실행 단계 출력기.

    그래프 워크플로우 실행 시 각 단계를 시각적으로 출력합니다.

    Example:
        printer = StepPrinter()
        printer.header("ANALYZE", "LLM 에이전트 실행")
        printer.result("ANALYZE", {"응답 길이": "100자"})
    """

    # 노드별 컬러 매핑
    NODE_COLORS = {
        "ANALYZE": Colors.BLUE,
        "EVALUATE": Colors.CYAN,
        "DECIDE": Colors.MAGENTA,
        "REGENERATE": Colors.YELLOW,
        "FINALIZE": Colors.GREEN,
    }

    def __init__(self) -> None:
        self._step_counter = 0

    def reset(self) -> None:
        """단계 카운터 초기화."""
        self._step_counter = 0

    def header(self, node_name: str, description: str) -> None:
        """단계 헤더 출력.

        Args:
            node_name: 노드 이름 (ANALYZE, EVALUATE, 등)
            description: 단계 설명
        """
        self._step_counter += 1
        color = self.NODE_COLORS.get(node_name, Colors.END)

        print()
        print(f"{color}{'-' * 60}{Colors.END}")
        print(f"{color}[{self._step_counter}] {node_name} - {description}{Colors.END}")
        print(f"{color}{'-' * 60}{Colors.END}")

    def result(self, node_name: str, results: dict[str, Any]) -> None:
        """단계 결과 출력.

        Args:
            node_name: 노드 이름
            results: 결과 키-값 딕셔너리
        """
        color = self.NODE_COLORS.get(node_name, Colors.END)

        for key, value in results.items():
            print(f"{color}    {key}: {value}{Colors.END}")


# 전역 StepPrinter 인스턴스 (nodes.py에서 사용)
step_printer = StepPrinter()
