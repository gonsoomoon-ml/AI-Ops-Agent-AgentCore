"""Workflow State Management.

그래프 노드 간 공유되는 워크플로우 상태 관리.

Reference:
    - https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent/src/utils/workflow_state.py
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ops_agent.evaluation.models import (
    CheckResult,
    EvalResult,
    EvalVerdict,
    ToolResult,
)


class WorkflowStatus(Enum):
    """워크플로우 최종 상태."""

    PENDING = "pending"
    PUBLISHED = "published"  # 정상 완료
    REJECTED = "rejected"    # 품질 미달
    ERROR = "error"          # 오류 발생


@dataclass
class OpsWorkflowState:
    """워크플로우 전역 상태.

    모든 노드가 공유하는 상태 객체입니다.
    각 노드는 필요한 데이터를 읽고 결과를 업데이트합니다.

    Attributes:
        prompt: 사용자 질문
        response: LLM 응답
        tool_results: 캡처된 도구 결과
        eval_result: 평가 결과
        check_results: 개별 검사 결과
        verdict: 최종 판정
        feedback: 재생성 피드백
        attempt: 현재 시도 횟수
        max_attempts: 최대 시도 횟수
        final_response: 최종 응답
        final_status: 최종 상태
        error: 오류 메시지 (있을 경우)
        metadata: 추가 메타데이터
    """

    # Input
    prompt: str

    # Agent execution
    response: str | None = None
    tool_results: list[ToolResult] = field(default_factory=list)

    # Evaluation
    eval_result: EvalResult | None = None
    check_results: list[CheckResult] = field(default_factory=list)

    # Decision
    verdict: EvalVerdict | None = None
    feedback: str | None = None

    # Control
    attempt: int = 0
    max_attempts: int = 2

    # Output
    final_response: str | None = None
    final_status: WorkflowStatus = WorkflowStatus.PENDING

    # Error handling
    error: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def reset_for_retry(self) -> None:
        """재시도를 위한 상태 초기화 (attempt, feedback 유지)."""
        self.response = None
        self.tool_results = []
        self.eval_result = None
        self.check_results = []
        self.verdict = None

    def to_dict(self) -> dict[str, Any]:
        """상태를 딕셔너리로 변환 (디버깅/로깅용)."""
        return {
            "prompt": self.prompt[:50] + "..." if len(self.prompt) > 50 else self.prompt,
            "response_length": len(self.response) if self.response else 0,
            "tool_results_count": len(self.tool_results),
            "verdict": self.verdict.value if self.verdict else None,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "final_status": self.final_status.value,
            "error": self.error,
        }


# ========== Global State Registry ==========
# Thread-safe global state management

_state_registry: dict[str, OpsWorkflowState] = {}
_registry_lock = threading.Lock()


def create_workflow_state(workflow_id: str, prompt: str, max_attempts: int = 2) -> OpsWorkflowState:
    """새 워크플로우 상태 생성 및 등록.

    Args:
        workflow_id: 워크플로우 고유 ID
        prompt: 사용자 질문
        max_attempts: 최대 시도 횟수

    Returns:
        OpsWorkflowState: 생성된 상태 객체
    """
    state = OpsWorkflowState(
        prompt=prompt,
        max_attempts=max_attempts,
    )

    with _registry_lock:
        _state_registry[workflow_id] = state

    return state


def get_workflow_state(workflow_id: str) -> OpsWorkflowState | None:
    """워크플로우 상태 조회.

    Args:
        workflow_id: 워크플로우 고유 ID

    Returns:
        OpsWorkflowState | None: 상태 객체 또는 None
    """
    with _registry_lock:
        return _state_registry.get(workflow_id)


def delete_workflow_state(workflow_id: str) -> None:
    """워크플로우 상태 삭제.

    Args:
        workflow_id: 워크플로우 고유 ID
    """
    with _registry_lock:
        _state_registry.pop(workflow_id, None)


# Current workflow ID for node access
# Note: Using module-level variable because async contexts don't share threading.local
_current_workflow_id: str | None = None


def set_current_workflow_id(workflow_id: str | None) -> None:
    """현재 워크플로우 ID 설정.

    Args:
        workflow_id: 워크플로우 고유 ID (None으로 초기화)
    """
    global _current_workflow_id
    _current_workflow_id = workflow_id


def get_current_workflow_id() -> str | None:
    """현재 워크플로우 ID 조회.

    Returns:
        str | None: 현재 워크플로우 ID
    """
    return _current_workflow_id


def get_current_workflow_state() -> OpsWorkflowState | None:
    """현재 스레드의 워크플로우 상태 조회.

    Returns:
        OpsWorkflowState | None: 현재 워크플로우 상태
    """
    workflow_id = get_current_workflow_id()
    if workflow_id:
        return get_workflow_state(workflow_id)
    return None
