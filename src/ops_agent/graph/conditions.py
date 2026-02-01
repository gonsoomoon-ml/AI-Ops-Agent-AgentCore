"""Conditional Edge Functions.

그래프의 조건부 라우팅을 위한 함수들.
GraphBuilder의 add_edge(condition=...) 에서 사용됩니다.

Note:
    조건 함수는 GraphState를 받지만, invocation_state는 아직 지원되지 않음.
    (https://github.com/strands-agents/sdk-python/issues/1124)
    따라서 우리의 OpsWorkflowState는 전역 레지스트리를 통해 접근합니다.

Reference:
    - /home/ubuntu/sample-deep-insight/self-hosted/src/graph/nodes.py
"""

import logging

from ops_agent.evaluation.models import EvalVerdict
from ops_agent.graph.state import get_current_workflow_state

logger = logging.getLogger(__name__)


def should_finalize(graph_state) -> bool:
    """FINALIZE 노드로 진행할지 결정.

    PASS 또는 BLOCK일 때 FINALIZE로 진행.

    Args:
        graph_state: Strands GraphState (사용하지 않음, 우리의 state 사용)

    Returns:
        bool: FINALIZE로 진행하면 True
    """
    state = get_current_workflow_state()
    if not state:
        logger.warning("[Condition] No workflow state found - defaulting to finalize")
        return True

    result = state.verdict in (EvalVerdict.PASS, EvalVerdict.BLOCK)
    logger.info(f"[Condition] should_finalize: {result} (verdict={state.verdict})")
    return result


def should_regenerate(graph_state) -> bool:
    """REGENERATE 노드로 진행할지 결정.

    REGENERATE 판정일 때 재생성으로 진행.

    Args:
        graph_state: Strands GraphState (사용하지 않음, 우리의 state 사용)

    Returns:
        bool: REGENERATE로 진행하면 True
    """
    state = get_current_workflow_state()
    if not state:
        logger.warning("[Condition] No workflow state found - defaulting to not regenerate")
        return False

    result = state.verdict == EvalVerdict.REGENERATE
    logger.info(f"[Condition] should_regenerate: {result} (verdict={state.verdict})")
    return result


def should_continue_analysis(graph_state) -> bool:
    """분석을 계속할지 결정 (REGENERATE → ANALYZE 루프).

    Args:
        graph_state: Strands GraphState (사용하지 않음)

    Returns:
        bool: 분석을 계속하면 True
    """
    state = get_current_workflow_state()
    if not state:
        return False

    # REGENERATE 노드를 거쳤으면 다시 ANALYZE로
    return state.attempt > 0 and state.verdict == EvalVerdict.REGENERATE


def is_error_state(graph_state) -> bool:
    """오류 상태인지 확인.

    Args:
        graph_state: Strands GraphState (사용하지 않음)

    Returns:
        bool: 오류 상태면 True
    """
    state = get_current_workflow_state()
    if not state:
        return False

    return state.error is not None
