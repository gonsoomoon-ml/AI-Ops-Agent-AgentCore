"""Ops AI Agent - Strands SDK 기반 에이전트.

운영 자동화를 위한 AI 에이전트입니다.
CloudWatch, Datadog, Knowledge Base 도구를 사용하여 모니터링 및 문제 분석을 수행합니다.

Reference:
    - Agent Factory Pattern: docs/research-guide-results.md 7.1
    - Message Injection Pattern: docs/research-guide-results.md 7.3
    - Evaluation Design: docs/evaluation-design.md
    - Graph Implementation: src/ops_agent/graph/

사용법:
    from ops_agent.agent import OpsAgent

    # Graph 기반 워크플로우 (평가 포함)
    agent = OpsAgent()
    response = agent.invoke("payment-service에서 500 에러 로그 보여줘")

    # 평가 없이 단순 호출
    agent = OpsAgent(enable_evaluation=False)
    response = agent.invoke("payment-service에서 500 에러 로그 보여줘")
"""

import logging
import os
import uuid

from strands import Agent
from strands.models import BedrockModel

# OTEL 스팬 래핑용 (트레이스 이름 커스터마이징)
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("ops-agent")
except ImportError:
    _tracer = None

from ops_agent.config import get_settings
from ops_agent.graph.runner import OpsAgentGraph
from ops_agent.telemetry import get_trace_attributes, setup_strands_observability
from ops_agent.graph.state import WorkflowStatus
from ops_agent.graph.util import Colors
from ops_agent.prompts import get_system_prompt
from ops_agent.tools.cloudwatch import get_cloudwatch_tools

# ========== 로깅 설정 ==========
logger = logging.getLogger(__name__)


class OpsAgent:
    """운영 자동화 AI 에이전트.

    Graph 기반 워크플로우를 사용하여 응답 품질 평가 및 자동 재생성을 수행합니다.

    Reference:
        - docs/research-guide-results.md - 7.1 Agent Factory Pattern
        - docs/evaluation-design.md
        - src/ops_agent/graph/ - Graph 기반 워크플로우

    사용 예시:
        # 기본 호출 (Graph 기반 평가 포함)
        agent = OpsAgent()
        response = agent.invoke("payment-service 500 에러 로그 보여줘")

        # 평가 비활성화 (단순 LLM 호출)
        agent = OpsAgent(enable_evaluation=False)
        response = agent.invoke("payment-service 500 에러 로그 보여줘")

        # Message Injection (테스트용)
        mock_results = [{"tool_name": "...", "tool_input": {...}, "tool_result": "..."}]
        response = agent.invoke_with_mock_history("에러 분석해줘", mock_results)
    """

    def __init__(
        self,
        enable_evaluation: bool = True,
        max_attempts: int = 2,
        verbose: bool = True,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """OpsAgent 초기화.

        Args:
            enable_evaluation: 응답 평가 활성화 여부 (기본: True)
            max_attempts: 최대 시도 횟수 (기본: 2)
            verbose: 상세 로깅 여부 (기본: True)
            session_id: 세션 ID (Langfuse 트레이스 그룹화용, 미지정 시 자동 생성)
            user_id: 사용자 ID (Langfuse 사용자별 분석용)
        """
        self.settings = get_settings()
        self.enable_evaluation = enable_evaluation
        self.max_attempts = max_attempts
        self.verbose = verbose

        # 세션 및 사용자 ID (Langfuse 트레이스용)
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id

        # Strands 관측성 설정 (Langfuse 연동)
        # STRANDS_OBSERVABILITY_MODE 환경 변수에 따라 설정됨
        self._observability_enabled = setup_strands_observability()

        # Graph 워크플로우 초기화 (평가 활성화 시)
        self._graph: OpsAgentGraph | None = None
        if enable_evaluation:
            self._graph = OpsAgentGraph(
                max_attempts=max_attempts,
                verbose=verbose,
            )

        logger.info(
            f"{Colors.GREEN}[OpsAgent] 초기화 "
            f"(model={self.settings.bedrock_model_id}, "
            f"evaluation={enable_evaluation}, "
            f"mode={'graph' if enable_evaluation else 'simple'}, "
            f"observability={self._observability_enabled}){Colors.END}"
        )

    @property
    def tools(self) -> list:
        """사용 가능한 도구 목록.

        CLOUDWATCH_MODE 설정에 따라 mock 또는 mcp 도구를 반환합니다.
        """
        tools = []

        # CloudWatch 도구 (mock 또는 mcp)
        tools.extend(get_cloudwatch_tools())

        # TODO: Phase 2 - Datadog, Knowledge Base
        # tools.extend(get_datadog_tools())
        # tools.extend(get_kb_tools())

        return tools

    def invoke(self, prompt: str) -> str:
        """에이전트 호출.

        평가 활성화 시 Graph 기반 워크플로우를 사용합니다.
        평가 비활성화 시 단순 LLM 호출을 수행합니다.

        Args:
            prompt: 사용자 질문

        Returns:
            에이전트 응답 문자열
        """
        if self.enable_evaluation and self._graph:
            return self._invoke_with_graph(prompt)
        else:
            return self._invoke_simple(prompt)

    async def stream_async(self, prompt: str):
        """스트리밍 에이전트 호출.

        AgentCore Runtime 스트리밍용 async generator.
        평가 활성화 시 Graph 스트리밍, 비활성화 시 직접 Agent 스트리밍.

        Args:
            prompt: 사용자 질문

        Yields:
            스트리밍 이벤트
        """
        if self.enable_evaluation and self._graph:
            async for event in self._stream_with_graph(prompt):
                yield event
        else:
            async for event in self._stream_simple(prompt):
                yield event

    async def _stream_with_graph(self, prompt: str):
        """Graph 기반 스트리밍 호출.

        Args:
            prompt: 사용자 질문

        Yields:
            스트리밍 이벤트
        """
        logger.info(f"{Colors.BLUE}[OpsAgent] Graph 스트리밍 실행{Colors.END}")

        # OTEL 스팬으로 래핑하여 Langfuse에서 "invoke_agent Strands Agents"로 표시
        if _tracer and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            with _tracer.start_as_current_span("invoke_agent OpsAgent (AgentCore)") as span:
                span.set_attribute("session.id", self.session_id or "")
                span.set_attribute("user.id", self.user_id or "")
                # Langfuse input/output 속성 추가
                span.set_attribute("gen_ai.prompt.0.content", prompt)
                span.set_attribute("input", prompt)

                output_text = ""
                async for event in self._graph.stream_async(prompt):
                    # 출력 텍스트 수집 (finalize 결과에서)
                    if isinstance(event, dict):
                        event_type = event.get("type", "")
                        if event_type == "multiagent_node_stream":
                            inner = event.get("event", {})
                            if isinstance(inner, dict):
                                result = inner.get("result")
                                if result and hasattr(result, "results"):
                                    finalize = result.results.get("finalize")
                                    if finalize and hasattr(finalize, "result"):
                                        msg = getattr(finalize.result, "message", None)
                                        if isinstance(msg, dict):
                                            for c in msg.get("content", []):
                                                if isinstance(c, dict) and "text" in c:
                                                    output_text = c["text"]
                    yield event

                # 출력 설정
                if output_text:
                    span.set_attribute("gen_ai.completion.0.content", output_text)
                    span.set_attribute("output", output_text)
        else:
            async for event in self._graph.stream_async(prompt):
                yield event

    async def _stream_simple(self, prompt: str):
        """단순 스트리밍 호출 (평가 없음).

        Args:
            prompt: 사용자 질문

        Yields:
            스트리밍 이벤트
        """
        logger.info(f"{Colors.BLUE}[OpsAgent] 단순 스트리밍: {prompt[:50]}...{Colors.END}")

        agent = self._create_agent()

        # OTEL 스팬으로 래핑 (Local 모드)
        if _tracer and self._observability_enabled:
            with _tracer.start_as_current_span("invoke_agent OpsAgent (Local)") as span:
                span.set_attribute("session.id", self.session_id or "")
                span.set_attribute("user.id", self.user_id or "")
                span.set_attribute("gen_ai.prompt.0.content", prompt)
                span.set_attribute("input", prompt)

                output_text = ""
                async for event in agent.stream_async(prompt):
                    # 출력 텍스트 수집
                    if isinstance(event, dict) and "data" in event:
                        text = event.get("data", "")
                        if isinstance(text, str):
                            output_text += text
                    yield event

                if output_text:
                    span.set_attribute("gen_ai.completion.0.content", output_text)
                    span.set_attribute("output", output_text)
        else:
            async for event in agent.stream_async(prompt):
                yield event

    def _invoke_with_graph(self, prompt: str) -> str:
        """Graph 기반 워크플로우로 호출.

        ANALYZE → EVALUATE → DECIDE → FINALIZE 워크플로우 실행.

        Args:
            prompt: 사용자 질문

        Returns:
            에이전트 응답 문자열
        """
        logger.info(f"{Colors.BLUE}[OpsAgent] Graph 워크플로우 실행{Colors.END}")

        # OTEL 스팬으로 래핑 (Local 모드)
        if _tracer and self._observability_enabled:
            with _tracer.start_as_current_span("invoke_agent OpsAgent (Local)") as span:
                span.set_attribute("session.id", self.session_id or "")
                span.set_attribute("user.id", self.user_id or "")
                span.set_attribute("gen_ai.prompt.0.content", prompt)
                span.set_attribute("input", prompt)

                result = self._graph.run(prompt)

                if result.final_status == WorkflowStatus.ERROR:
                    logger.error(f"{Colors.RED}[OpsAgent] 워크플로우 오류: {result.error}{Colors.END}")
                    raise RuntimeError(f"Workflow error: {result.error}")

                response = result.final_response or ""
                span.set_attribute("gen_ai.completion.0.content", response)
                span.set_attribute("output", response)
                return response
        else:
            result = self._graph.run(prompt)

            if result.final_status == WorkflowStatus.ERROR:
                logger.error(f"{Colors.RED}[OpsAgent] 워크플로우 오류: {result.error}{Colors.END}")
                raise RuntimeError(f"Workflow error: {result.error}")

            return result.final_response or ""

    def _invoke_simple(self, prompt: str) -> str:
        """단순 LLM 호출 (평가 없음).

        Args:
            prompt: 사용자 질문

        Returns:
            에이전트 응답 문자열
        """
        logger.info(f"{Colors.BLUE}[OpsAgent] 단순 호출: {prompt[:50]}...{Colors.END}")

        try:
            agent = self._create_agent()

            # OTEL 스팬으로 래핑 (Local 모드)
            if _tracer and self._observability_enabled:
                with _tracer.start_as_current_span("invoke_agent OpsAgent (Local)") as span:
                    span.set_attribute("session.id", self.session_id or "")
                    span.set_attribute("user.id", self.user_id or "")
                    span.set_attribute("gen_ai.prompt.0.content", prompt)
                    span.set_attribute("input", prompt)

                    result = agent(prompt)
                    response = result.message["content"][0]["text"]

                    span.set_attribute("gen_ai.completion.0.content", response)
                    span.set_attribute("output", response)
            else:
                result = agent(prompt)
                response = result.message["content"][0]["text"]

            logger.info(f"{Colors.GREEN}[OpsAgent] 완료: {len(response)}자{Colors.END}")
            return response

        except Exception as e:
            logger.error(f"{Colors.RED}[OpsAgent] 오류: {e}{Colors.END}")
            raise

    def _create_agent(self, messages: list[dict] | None = None) -> Agent:
        """Strands Agent 생성.

        Reference: docs/research-guide-results.md - 7.1 Agent Factory Pattern

        Args:
            messages: Message Injection용 대화 히스토리

        Returns:
            Agent 인스턴스
        """
        model = BedrockModel(
            model_id=self.settings.bedrock_model_id,
            region_name=self.settings.aws_region,
            temperature=self.settings.bedrock_temperature,
            max_tokens=self.settings.bedrock_max_tokens,
        )

        system_prompt = get_system_prompt()

        # Langfuse 트레이스 속성 생성 (관측성 활성화 시)
        # 세션별, 사용자별로 트레이스를 그룹화하기 위한 속성
        trace_attributes = get_trace_attributes(
            session_id=self.session_id,
            user_id=self.user_id,
        )

        # Agent 공통 파라미터
        agent_kwargs = {
            "model": model,
            "tools": self.tools,
            "system_prompt": system_prompt,
        }

        # 트레이스 속성이 있으면 추가
        if trace_attributes:
            agent_kwargs["trace_attributes"] = trace_attributes

        # Message Injection 모드
        if messages:
            agent_kwargs["messages"] = messages

        return Agent(**agent_kwargs)

    def invoke_with_mock_history(
        self,
        prompt: str,
        mock_tool_results: list[dict],
    ) -> str:
        """Message Injection으로 에이전트 호출 (테스트용).

        Reference: docs/research-guide-results.md - 7.3 Message Injection Pattern

        실제 도구 호출 없이 미리 정의된 도구 결과를 주입합니다.

        Args:
            prompt: 사용자 질문
            mock_tool_results: Mock 도구 결과 목록
                - tool_name: 도구 이름
                - tool_input: 도구 입력
                - tool_result: 도구 결과 (JSON 문자열)

        Returns:
            에이전트 응답 문자열

        사용 예시:
            mock_results = [{
                "tool_name": "cloudwatch_filter_log_events",
                "tool_input": {"log_group_name": "/aws/lambda/payment"},
                "tool_result": '{"events": [...]}'
            }]
            response = agent.invoke_with_mock_history("분석해줘", mock_results)
        """
        logger.info(
            f"{Colors.YELLOW}[OpsAgent] Message Injection 호출: "
            f"{len(mock_tool_results)}개 도구 결과{Colors.END}"
        )

        messages = self._build_mock_messages(mock_tool_results)

        try:
            agent = self._create_agent(messages=messages)
            result = agent(prompt)

            response = result.message["content"][0]["text"]

            logger.info(f"{Colors.GREEN}[OpsAgent] 완료: {len(response)}자{Colors.END}")
            return response

        except Exception as e:
            logger.error(f"{Colors.RED}[OpsAgent] 오류: {e}{Colors.END}")
            raise

    def _build_mock_messages(self, mock_tool_results: list[dict]) -> list[dict]:
        """Mock 메시지 히스토리 생성.

        Reference: docs/research-guide-results.md - 7.3
        """
        messages = []

        for i, mock in enumerate(mock_tool_results):
            tool_use_id = f"mock_{i:03d}"

            messages.append({
                "role": "assistant",
                "content": [{
                    "toolUse": {
                        "toolUseId": tool_use_id,
                        "name": mock["tool_name"],
                        "input": mock["tool_input"],
                    }
                }],
            })

            messages.append({
                "role": "user",
                "content": [{
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "status": "success",
                        "content": [{"text": mock["tool_result"]}],
                    }
                }],
            })

        return messages


# ========== 테스트 ==========

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("\n" + "=" * 50)
    print("OpsAgent 테스트 (Graph 기반 평가)")
    print("=" * 50 + "\n")

    agent = OpsAgent(enable_evaluation=True)
    response = agent.invoke("payment-service에서 500 에러 로그 보여줘")
    print(response)
