"""FunctionNode - Python 함수를 그래프 노드로 래핑.

Strands GraphBuilder는 Agent 또는 MultiAgentBase만 노드로 지원합니다.
FunctionNode는 일반 Python 함수를 MultiAgentBase로 래핑하여 GraphBuilder에서 사용할 수 있게 합니다.

왜 필요한가?
    GraphBuilder.add_node()는 Agent 또는 MultiAgentBase만 받음
    → 일반 Python 함수를 사용하려면 래퍼가 필요

동작 방식:
    Python Function → FunctionNode → MultiAgentBase → GraphBuilder

Reference:
    - https://github.com/strands-agents/sdk-python/issues/544
    - /home/ubuntu/sample-deep-insight/self-hosted/src/utils/strands_sdk_utils.py

사용법:
    from ops_agent.graph.function_node import FunctionNode

    def my_node(task=None, **kwargs):
        return {"text": "result"}

    node = FunctionNode(func=my_node, name="my_node")
    builder.add_node(node, "my_node")
"""

import asyncio
import logging
from typing import Any, Callable

from strands.agent.agent_result import AgentResult
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.types.content import ContentBlock, Message

logger = logging.getLogger(__name__)


class FunctionNode(MultiAgentBase):
    """Python 함수를 그래프 노드로 실행하는 래퍼 클래스.

    Strands GraphBuilder는 Agent 또는 MultiAgentBase만 노드로 지원합니다.
    이 클래스는 일반 Python 함수를 그래프 노드로 사용할 수 있게 래핑합니다.

    래핑되는 함수 요구사항:
        - task=None과 **kwargs를 인자로 받아야 함
        - {"text": "..."} 형태의 dict를 반환해야 함

    Example:
        def analyze_node(task=None, **kwargs):
            # 처리 로직...
            return {"text": "분석 완료", "score": 0.95}

        node = FunctionNode(func=analyze_node, name="analyze")
        builder.add_node(node, "analyze")
    """

    def __init__(self, func: Callable, name: str | None = None) -> None:
        """FunctionNode 초기화.

        Args:
            func: 래핑할 함수 (sync 또는 async 모두 가능)
            name: 노드 이름 (기본값: 함수 이름)
        """
        super().__init__()
        self.func = func
        self.name = name or func.__name__

    def __call__(self, task: Any = None, **kwargs) -> Any:
        """동기 실행 (호환성용)."""
        if asyncio.iscoroutinefunction(self.func):
            return asyncio.run(self.func(task=task, **kwargs))
        else:
            return self.func(task=task, **kwargs)

    async def invoke_async(
        self,
        task: Any = None,
        invocation_state: dict | None = None,
        **kwargs,
    ) -> MultiAgentResult:
        """비동기 실행 (MultiAgentBase 필수 메서드).

        GraphBuilder가 노드를 실행할 때 이 메서드를 호출합니다.

        Args:
            task: 입력 태스크 (보통 프롬프트 문자열)
            invocation_state: 그래프 공유 상태 (사용 안함, 전역 레지스트리 사용)
            **kwargs: 추가 인자

        Returns:
            MultiAgentResult: 래핑된 함수 출력
        """
        # 함수 실행 (sync 또는 async)
        if asyncio.iscoroutinefunction(self.func):
            response = await self.func(task=task, **kwargs)
        else:
            response = self.func(task=task, **kwargs)

        # 응답이 {"text": ...} 형태인지 확인
        if not isinstance(response, dict):
            response = {"text": str(response)}
        if "text" not in response:
            response["text"] = str(response)

        # AgentResult로 래핑
        agent_result = AgentResult(
            stop_reason="end_turn",
            message=Message(
                role="assistant",
                content=[ContentBlock(text=str(response["text"]))],
            ),
            metrics={},
            state={},
        )

        # MultiAgentResult 반환
        return MultiAgentResult(
            status=Status.COMPLETED,
            results={self.name: NodeResult(result=agent_result)},
        )

    async def stream_async(
        self,
        task: Any = None,
        invocation_state: dict | None = None,
        **kwargs,
    ):
        """스트리밍 비동기 실행 (Graph 스트리밍용).

        래핑된 함수가 async generator인 경우 스트리밍 이벤트를 전달합니다.
        일반 함수인 경우 invoke_async로 폴백합니다.

        Args:
            task: 입력 태스크
            invocation_state: 그래프 공유 상태
            **kwargs: 추가 인자

        Yields:
            스트리밍 이벤트 또는 최종 MultiAgentResult
        """
        import inspect

        # Check if function is an async generator
        if inspect.isasyncgenfunction(self.func):
            # Async generator function - yield events from it
            final_response = None
            async for event in self.func(task=task, **kwargs):
                # Check if this is the final result (dict with "text" key and "_final" marker)
                if isinstance(event, dict) and event.get("_final"):
                    final_response = event
                else:
                    # Yield streaming event as-is
                    yield event

            # Build final MultiAgentResult from the captured response
            if final_response is None:
                final_response = {"text": ""}

            # Remove internal marker
            final_response.pop("_final", None)

            agent_result = AgentResult(
                stop_reason="end_turn",
                message=Message(
                    role="assistant",
                    content=[ContentBlock(text=str(final_response.get("text", "")))],
                ),
                metrics={},
                state={},
            )

            # Wrap in dict with "result" key for Graph compatibility
            # Graph._execute_node checks `if "result" in event:` to detect completion
            yield {
                "result": MultiAgentResult(
                    status=Status.COMPLETED,
                    results={self.name: NodeResult(result=agent_result)},
                )
            }
        else:
            # Regular function - fall back to invoke_async
            result = await self.invoke_async(task=task, invocation_state=invocation_state, **kwargs)
            # Wrap in dict with "result" key for Graph compatibility
            yield {"result": result}
