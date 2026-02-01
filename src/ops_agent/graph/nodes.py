"""Graph Node Implementations.

각 노드는 워크플로우의 한 단계를 담당합니다.
FunctionNode로 래핑되어 GraphBuilder에서 사용됩니다.

Nodes:
    - analyze_node: LLM 에이전트 실행 및 도구 호출 (스트리밍)
    - evaluate_node: 응답 품질 평가
    - decide_node: 평가 결과 기반 판정
    - regenerate_node: 재생성 피드백 준비
    - finalize_node: 최종 출력 결정
"""

import logging
from typing import Any

from strands import Agent
from strands.models import BedrockModel
from strands.types.content import SystemContentBlock

from ops_agent.config import get_settings
from ops_agent.evaluation.evaluator import OpsAgentEvaluator
from ops_agent.evaluation.models import EvalVerdict
from ops_agent.graph.state import get_current_workflow_state, WorkflowStatus
from ops_agent.graph.util import (
    Colors,
    ToolResultExtractor,
    build_retry_prompt,
    step_printer,
)
from ops_agent.prompts import get_system_prompt
from ops_agent.tools.cloudwatch import cloudwatch_filter_log_events

logger = logging.getLogger(__name__)


# ==========================================================================
# 에이전트 생성
# ==========================================================================
def _create_agent() -> Agent:
    """Strands Agent 생성.

    프롬프트 캐싱 적용:
        - 시스템 프롬프트에 cachePoint 추가 (최대 90% 비용 절감)
        - 도구 정의에도 캐싱 적용 (cache_tools)
    """
    settings = get_settings()

    model = BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=settings.bedrock_temperature,
        max_tokens=settings.bedrock_max_tokens,
        cache_tools="default",
    )

    system_prompt_text = get_system_prompt()

    # 프롬프트 캐싱: SystemContentBlock + cachePoint
    system_prompt = [
        SystemContentBlock(text=system_prompt_text),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]

    tools = [
        cloudwatch_filter_log_events,
        # TODO: Phase 2
        # datadog_get_metrics,
        # kb_retrieve,
    ]

    return Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )


# ==========================================================================
# 노드 구현
# ==========================================================================
# 각 노드:
#   - task=None, **kwargs 인자 (FunctionNode 호환성)
#   - get_current_workflow_state()로 상태 접근
#   - {"text": ...} 형태 반환


def reset_step_counter() -> None:
    """워크플로우 시작 시 단계 카운터 초기화."""
    step_printer.reset()


async def analyze_node(task=None, **kwargs):
    """ANALYZE: LLM 에이전트 실행 및 도구 호출 (스트리밍).

    Async generator로 스트리밍 이벤트를 전달합니다.
    마지막에 _final=True가 포함된 dict를 yield합니다.

    Yields:
        스트리밍 이벤트 (agent.stream_async)
        마지막: {"text": response, "_final": True}
    """
    state = get_current_workflow_state()
    if not state:
        raise RuntimeError("No workflow state found")

    step_printer.header("ANALYZE", f"LLM 에이전트 실행 (시도 {state.attempt + 1}/{state.max_attempts})")

    try:
        # 재시도 시 피드백 포함 프롬프트
        if state.attempt > 0 and state.feedback:
            current_prompt = build_retry_prompt(state.prompt, state.feedback)
            logger.info(f"{Colors.YELLOW}[ANALYZE] 피드백 반영 프롬프트 사용{Colors.END}")
        else:
            current_prompt = state.prompt

        # Strands Agent 스트리밍 실행
        agent = _create_agent()

        async for event in agent.stream_async(current_prompt):
            yield event

        # 응답 추출 (마지막 assistant 메시지)
        response = ""
        if hasattr(agent, "messages") and agent.messages:
            for msg in reversed(agent.messages):
                if msg.get("role") == "assistant":
                    for content in msg.get("content", []):
                        if isinstance(content, dict) and "text" in content:
                            response = content["text"]
                            break
                    if response:
                        break

        # 도구 결과 추출
        tool_results = []
        if hasattr(agent, "messages") and agent.messages:
            tool_results = ToolResultExtractor.from_messages(agent.messages)

        # 상태 업데이트
        state.response = response
        state.tool_results = tool_results

        step_printer.result("ANALYZE", {
            "응답 길이": f"{len(response)}자",
            "도구 호출": f"{len(tool_results)}건",
        })

        # 최종 결과 (_final 마커)
        yield {
            "text": response,
            "tool_results_count": len(tool_results),
            "_final": True,
        }

    except Exception as e:
        logger.error(f"{Colors.RED}[ANALYZE] 오류: {e}{Colors.END}")
        state.error = str(e)
        state.final_status = WorkflowStatus.ERROR
        raise


def evaluate_node(task=None, **kwargs) -> dict[str, Any]:
    """EVALUATE: 응답 품질 평가.

    Returns:
        {"text": score_info, "overall_score": float, "check_count": int}
    """
    state = get_current_workflow_state()
    if not state:
        raise RuntimeError("No workflow state found")

    step_printer.header("EVALUATE", "응답 품질 평가")

    try:
        evaluator = OpsAgentEvaluator()
        eval_result = evaluator.evaluate(
            response=state.response or "",
            tool_results=state.tool_results,
        )

        state.eval_result = eval_result
        state.check_results = eval_result.check_results

        step_printer.result("EVALUATE", {
            "점수": f"{eval_result.overall_score:.2f}",
            "검사 항목": f"{len(eval_result.check_results)}개",
        })

        return {
            "text": f"Score: {eval_result.overall_score:.2f}",
            "overall_score": eval_result.overall_score,
            "check_count": len(eval_result.check_results),
        }

    except Exception as e:
        logger.error(f"{Colors.RED}[EVALUATE] 오류: {e}{Colors.END}")
        state.error = str(e)
        raise


def decide_node(task=None, **kwargs) -> dict[str, Any]:
    """DECIDE: 평가 결과 기반 판정.

    판정 로직:
        - score >= 0.7: PASS
        - score < 0.3: BLOCK
        - attempt >= max_attempts: PASS
        - otherwise: REGENERATE

    Returns:
        {"text": verdict_info, "verdict": str, "score": float, "reason": str}
    """
    state = get_current_workflow_state()
    if not state:
        raise RuntimeError("No workflow state found")

    step_printer.header("DECIDE", "판정 결정")

    if not state.eval_result:
        state.verdict = EvalVerdict.PASS
        logger.warning(f"{Colors.YELLOW}[DECIDE] 평가 결과 없음 - PASS{Colors.END}")
        return {"text": "PASS (no eval result)", "verdict": "pass", "reason": "no_eval_result"}

    score = state.eval_result.overall_score

    # 판정 로직
    if score >= 0.7:
        state.verdict = EvalVerdict.PASS
        reason = "score_pass"
    elif score < 0.3:
        state.verdict = EvalVerdict.BLOCK
        reason = "score_block"
    elif state.attempt >= state.max_attempts - 1:
        state.verdict = EvalVerdict.PASS
        reason = "max_attempts_reached"
        logger.warning(f"{Colors.YELLOW}[DECIDE] 최대 시도 도달 - 현재 응답으로 진행{Colors.END}")
    else:
        state.verdict = EvalVerdict.REGENERATE
        reason = "regenerate"

    step_printer.result("DECIDE", {
        "판정": state.verdict.value.upper(),
        "점수": f"{score:.2f}",
        "사유": reason,
    })

    return {
        "text": f"{state.verdict.value.upper()} (score={score:.2f})",
        "verdict": state.verdict.value,
        "score": score,
        "reason": reason,
    }


def regenerate_node(task=None, **kwargs) -> dict[str, Any]:
    """REGENERATE: 재생성 피드백 준비.

    Returns:
        {"text": feedback_info, "attempt": int, "feedback_length": int}
    """
    state = get_current_workflow_state()
    if not state:
        raise RuntimeError("No workflow state found")

    step_printer.header("REGENERATE", "재생성 피드백 준비")

    # 피드백 설정
    if state.eval_result and state.eval_result.feedback:
        state.feedback = state.eval_result.feedback
    else:
        state.feedback = "이전 응답의 품질이 부족합니다. 도구 결과를 더 정확하게 인용해주세요."

    # 시도 횟수 증가 및 상태 초기화
    state.attempt += 1
    state.reset_for_retry()

    step_printer.result("REGENERATE", {
        "다음 시도": f"{state.attempt + 1}/{state.max_attempts}",
        "피드백 길이": f"{len(state.feedback) if state.feedback else 0}자",
    })

    return {
        "text": f"Regenerating (attempt {state.attempt + 1})",
        "attempt": state.attempt,
        "feedback_length": len(state.feedback) if state.feedback else 0,
    }


def finalize_node(task=None, **kwargs) -> dict[str, Any]:
    """FINALIZE: 최종 출력 결정.

    Returns:
        {"text": final_response, "final_status": str, "response_length": int}
    """
    state = get_current_workflow_state()
    if not state:
        raise RuntimeError("No workflow state found")

    step_printer.header("FINALIZE", "최종 출력 결정")

    if state.verdict == EvalVerdict.PASS:
        state.final_response = state.response
        state.final_status = WorkflowStatus.PUBLISHED
        status_msg = "PUBLISHED"

    elif state.verdict == EvalVerdict.BLOCK:
        state.final_response = f"⚠️ 응답 품질 검증 주의\n\n{state.response}"
        state.final_status = WorkflowStatus.REJECTED
        status_msg = "REJECTED"

    else:
        state.final_response = state.response
        state.final_status = WorkflowStatus.PUBLISHED
        status_msg = "PUBLISHED (max attempts)"

    step_printer.result("FINALIZE", {
        "상태": status_msg,
        "응답 길이": f"{len(state.final_response or '')}자",
    })

    return {
        "text": state.final_response or "",
        "final_status": state.final_status.value,
        "response_length": len(state.final_response or ""),
    }
