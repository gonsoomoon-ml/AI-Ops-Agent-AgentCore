"""OpsAgent Graph Runner.

Strands GraphBuilder를 사용한 그래프 기반 워크플로우 실행기.

Reference:
    - https://strandsagents.com/latest/user-guide/concepts/multi-agent/graph/
    - /home/ubuntu/sample-deep-insight/self-hosted/src/graph/builder.py

사용법:
    graph = OpsAgentGraph()
    result = graph.run("payment-service에서 500 에러 로그 보여줘")
    print(result.final_response)
"""

import logging
import uuid

from strands.multiagent import GraphBuilder

from ops_agent.graph.conditions import should_finalize, should_regenerate
from ops_agent.graph.function_node import FunctionNode
from ops_agent.graph.nodes import (
    analyze_node,
    decide_node,
    evaluate_node,
    finalize_node,
    regenerate_node,
    reset_step_counter,
)
from ops_agent.graph.state import (
    OpsWorkflowState,
    WorkflowStatus,
    create_workflow_state,
    delete_workflow_state,
    set_current_workflow_id,
    get_current_workflow_state,
)
from ops_agent.graph.util import Colors

logger = logging.getLogger(__name__)


def build_ops_graph(max_node_executions: int = 15) -> "Graph":
    """Build OpsAgent evaluation graph.

    Graph Structure:
        ANALYZE → EVALUATE → DECIDE → FINALIZE → END
                                ↓
                           REGENERATE
                                ↓
                            ANALYZE (loop)

    Args:
        max_node_executions: Maximum node executions to prevent infinite loops

    Returns:
        Compiled Graph instance
    """
    builder = GraphBuilder()

    # Create FunctionNode wrappers for each node
    analyze = FunctionNode(func=analyze_node, name="analyze")
    evaluate = FunctionNode(func=evaluate_node, name="evaluate")
    decide = FunctionNode(func=decide_node, name="decide")
    regenerate = FunctionNode(func=regenerate_node, name="regenerate")
    finalize = FunctionNode(func=finalize_node, name="finalize")

    # Add nodes to graph
    builder.add_node(analyze, "analyze")
    builder.add_node(evaluate, "evaluate")
    builder.add_node(decide, "decide")
    builder.add_node(regenerate, "regenerate")
    builder.add_node(finalize, "finalize")

    # Set entry point
    builder.set_entry_point("analyze")

    # Define edges
    builder.add_edge("analyze", "evaluate")
    builder.add_edge("evaluate", "decide")

    # Conditional edges from decide
    builder.add_edge("decide", "finalize", condition=should_finalize)
    builder.add_edge("decide", "regenerate", condition=should_regenerate)

    # Regenerate loops back to analyze
    builder.add_edge("regenerate", "analyze")

    # Set execution limits
    builder.set_max_node_executions(max_node_executions)

    return builder.build()


class OpsAgentGraph:
    """그래프 기반 OpsAgent 워크플로우.

    Strands GraphBuilder를 사용하여 선언적으로 그래프를 정의합니다.

    그래프 구조:
        ANALYZE → EVALUATE → DECIDE → FINALIZE
                                ↓
                           REGENERATE
                                ↓
                            ANALYZE (loop)

    Example:
        graph = OpsAgentGraph(max_attempts=2)
        result = graph.run("payment-service에서 500 에러 로그 보여줘")
        print(result.final_response)
    """

    def __init__(
        self,
        max_attempts: int = 2,
        max_node_executions: int = 15,
        verbose: bool = True,
    ) -> None:
        """그래프 초기화.

        Args:
            max_attempts: 최대 시도 횟수
            max_node_executions: 최대 노드 실행 횟수 (무한 루프 방지)
            verbose: 상세 로깅 여부
        """
        self.max_attempts = max_attempts
        self.max_node_executions = max_node_executions
        self.verbose = verbose

        # Build the graph
        self._graph = build_ops_graph(max_node_executions=max_node_executions)

    def run(self, prompt: str) -> OpsWorkflowState:
        """워크플로우 실행.

        Args:
            prompt: 사용자 질문

        Returns:
            OpsWorkflowState: 최종 워크플로우 상태
        """
        workflow_id = str(uuid.uuid4())

        if self.verbose:
            self._print_header(prompt)

        # Create and register workflow state
        state = create_workflow_state(
            workflow_id=workflow_id,
            prompt=prompt,
            max_attempts=self.max_attempts,
        )

        # Set current workflow ID for node access
        set_current_workflow_id(workflow_id)

        # Reset step counter for new workflow
        reset_step_counter()

        try:
            # Execute graph
            result = self._graph(prompt)

            if self.verbose:
                self._print_result(result)

            # Get final state from registry
            final_state = get_current_workflow_state()
            if final_state:
                if self.verbose:
                    self._print_summary(final_state)
                return final_state
            else:
                # Fallback to original state
                return state

        except Exception as e:
            logger.error(f"{Colors.RED}[Graph] 워크플로우 오류: {e}{Colors.END}")
            state.final_status = WorkflowStatus.ERROR
            state.error = str(e)
            return state

        finally:
            # Cleanup
            set_current_workflow_id(None)
            delete_workflow_state(workflow_id)

    async def stream_async(self, prompt: str):
        """스트리밍 워크플로우 실행.

        AgentCore Runtime 스트리밍용 async generator.
        Graph.stream_async()를 사용하여 실시간 이벤트를 전달합니다.

        Args:
            prompt: 사용자 질문

        Yields:
            스트리밍 이벤트
        """
        workflow_id = str(uuid.uuid4())

        if self.verbose:
            logger.info(f"{Colors.BLUE}[Graph] 스트리밍 워크플로우 시작{Colors.END}")

        # Create and register workflow state
        state = create_workflow_state(
            workflow_id=workflow_id,
            prompt=prompt,
            max_attempts=self.max_attempts,
        )

        # Set current workflow ID for node access
        set_current_workflow_id(workflow_id)

        # Reset step counter for new workflow
        reset_step_counter()

        try:
            # Execute graph with streaming
            async for event in self._graph.stream_async(prompt):
                yield event

            if self.verbose:
                logger.info(f"{Colors.GREEN}[Graph] 스트리밍 워크플로우 완료{Colors.END}")

        except Exception as e:
            logger.error(f"{Colors.RED}[Graph] 스트리밍 오류: {e}{Colors.END}")
            raise

        finally:
            # Cleanup
            set_current_workflow_id(None)
            delete_workflow_state(workflow_id)

    def _print_header(self, prompt: str) -> None:
        """워크플로우 시작 헤더 출력."""
        print()
        print(f"{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"{Colors.BOLD} OpsAgent Graph Workflow{Colors.END}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"  Prompt: {prompt[:50]}...")
        print(f"  Max Attempts: {self.max_attempts}")
        print(f"{'=' * 60}")
        print()

    def _print_result(self, result) -> None:
        """GraphResult 출력."""
        print()
        print(f"{Colors.CYAN}[Graph] Execution completed{Colors.END}")
        print(f"  Status: {result.status}")
        if hasattr(result, 'execution_order'):
            nodes = [n.node_id for n in result.execution_order]
            print(f"  Execution order: {' → '.join(nodes)}")

    def _print_summary(self, state: OpsWorkflowState) -> None:
        """워크플로우 완료 요약."""
        print()
        print(f"{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"{Colors.BOLD} Workflow Complete{Colors.END}")
        print(f"{'=' * 60}")
        print(f"  Status: {state.final_status.value}")
        print(f"  Attempts: {state.attempt + 1}")
        print(f"  Verdict: {state.verdict.value if state.verdict else 'N/A'}")
        if state.eval_result:
            print(f"  Score: {state.eval_result.overall_score:.2f}")
        print(f"  Response Length: {len(state.final_response or '')} chars")
        print(f"{'=' * 60}")
        print()

    def print_graph_structure(self) -> None:
        """그래프 구조 출력."""
        print("""
┌─────────────────────────────────────────────────────────────┐
│                  OpsAgent Evaluation Graph                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   START                                                     │
│     │                                                       │
│     ▼                                                       │
│   ┌──────────┐                                              │
│   │ ANALYZE  │  LLM 에이전트 실행, 도구 호출                  │
│   └────┬─────┘                                              │
│        │                                                    │
│        ▼                                                    │
│   ┌──────────┐                                              │
│   │ EVALUATE │  응답 품질 평가 (CloudWatch, Datadog, KB)     │
│   └────┬─────┘                                              │
│        │                                                    │
│        ▼                                                    │
│   ┌──────────┐                                              │
│   │  DECIDE  │  판정 (PASS / REGENERATE / BLOCK)            │
│   └────┬─────┘                                              │
│        │                                                    │
│        ├── should_finalize() ──▶ ┌──────────┐               │
│        │                         │ FINALIZE │ → END         │
│        │                         └──────────┘               │
│        │                                                    │
│        └── should_regenerate() ─▶ ┌────────────┐            │
│                                   │ REGENERATE │            │
│                                   └──────┬─────┘            │
│                                          │                  │
│                                          └───▶ ANALYZE      │
│                                               (loop back)   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
        """)
