"""OpsAgent AgentCore Runtime Entrypoint (Streaming).

AgentCore Runtime 배포를 위한 진입점 파일입니다.
OpsAgent를 BedrockAgentCoreApp으로 래핑하고 실시간 토큰 스트리밍을 지원합니다.

Reference:
    - docs/research-guide-results.md - Section 7.2 (4-Line Pattern)
    - amazon-bedrock-agentcore-samples/03-integrations/observability/

Usage:
    # Local testing
    python entrypoint.py

    # Deployed via AgentCore Starter Toolkit
    agentcore configure --entrypoint entrypoint.py
    agentcore launch
"""

import logging
import sys
from pathlib import Path

# ops_agent 임포트를 위한 src 경로 추가
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from ops_agent.agent import OpsAgent
from ops_agent.config import get_settings

# ==========================================================================
# 로깅 설정
# ==========================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==========================================================================
# 이벤트 추출기
# ==========================================================================
class StreamingEventExtractor:
    """Graph 스트리밍 이벤트에서 텍스트 추출.

    지원하는 이벤트 구조:

    1. analyze 노드 - 토큰 델타 (두 가지 형태):
       - event.event.contentBlockDelta.delta.text
       - event.delta.text

    2. finalize 노드 - 최종 결과:
       - event.result.results["finalize"].result.message.content[].text
    """

    @staticmethod
    def extract(event: dict) -> tuple[str | None, bool]:
        """이벤트에서 텍스트 추출.

        Args:
            event: Graph 스트리밍 이벤트

        Returns:
            (텍스트, is_delta) - 텍스트가 없으면 (None, False)
        """
        if not isinstance(event, dict):
            return None, False

        event_type = event.get("type", "")
        node_id = event.get("node_id", "")

        # analyze 노드: 토큰 델타
        if event_type == "multiagent_node_stream" and node_id == "analyze":
            text = StreamingEventExtractor._extract_delta(event.get("event", {}))
            if text:
                return text, True

        # finalize 노드: 최종 결과
        if event_type in ("multiagent_node_stream", "multiagent_node_stop") and node_id == "finalize":
            text = StreamingEventExtractor._extract_finalize(event.get("event", {}))
            if text:
                return text, False

        return None, False

    @staticmethod
    def _extract_delta(inner: dict) -> str | None:
        """델타 이벤트에서 텍스트 추출."""
        if not isinstance(inner, dict):
            return None

        # 형태 1: event.event.contentBlockDelta.delta.text
        nested = inner.get("event", {})
        if isinstance(nested, dict) and "contentBlockDelta" in nested:
            delta = nested["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                return delta["text"]

        # 형태 2: event.delta.text
        delta = inner.get("delta", {})
        if isinstance(delta, dict) and "text" in delta:
            return delta["text"]

        return None

    @staticmethod
    def _extract_finalize(inner: dict) -> str | None:
        """finalize 결과에서 텍스트 추출."""
        if not isinstance(inner, dict):
            return None

        result = inner.get("result")
        if not result or not hasattr(result, "results"):
            return None

        finalize_result = result.results.get("finalize")
        if not finalize_result:
            return None

        if not hasattr(finalize_result, "result") or not hasattr(finalize_result.result, "message"):
            return None

        message = finalize_result.result.message
        if not isinstance(message, dict) or "content" not in message:
            return None

        for content in message["content"]:
            if isinstance(content, dict) and "text" in content:
                return content["text"]

        return None


# ==========================================================================
# 에이전트 초기화
# ==========================================================================
settings = get_settings()

logger.info("Initializing OpsAgent for AgentCore Runtime...")
logger.info(f"  Model: {settings.bedrock_model_id}")
logger.info(f"  Region: {settings.aws_region}")

agent = OpsAgent(enable_evaluation=True, max_attempts=2, verbose=False)

# ==========================================================================
# 런타임 앱 및 엔트리포인트
# ==========================================================================
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict):
    """AgentCore Runtime 스트리밍 entrypoint.

    Args:
        payload: 요청 페이로드
            - prompt: 사용자 질문/요청
            - session_id: (선택) 대화 세션 ID
            - raw_events: (선택) 디버그용 원시 이벤트 반환 모드

    Yields:
        {"type": "delta", "content": "..."} - 스트리밍 토큰
    """
    # 사용자 프롬프트 (필수)
    prompt = payload.get("prompt", "")

    # 세션 ID (선택) - 대화 컨텍스트 유지용
    session_id = payload.get("session_id")

    # 디버그 모드 (선택, 기본값: False)
    # - False: 텍스트만 추출하여 깔끔한 형식으로 반환
    # - True: Graph 원시 이벤트 그대로 반환 (디버깅용)
    # 사용법: invoke.py --raw
    raw_events = payload.get("raw_events", False)

    logger.info(f"Request: {prompt[:100]}...")
    if session_id:
        logger.info(f"Session: {session_id}")

    try:
        # 스트리밍 여부 추적 (중복 방지용)
        has_streamed = False

        async for event in agent.stream_async(prompt):
            if raw_events:
                # 디버그 모드: 원시 이벤트 그대로 전달
                yield event
            else:
                # 일반 모드: 텍스트만 추출
                text, is_delta = StreamingEventExtractor.extract(event)
                if text:
                    if is_delta:
                        # 토큰 델타 - 실시간 스트리밍
                        has_streamed = True
                        yield {"type": "delta", "content": text}
                    elif not has_streamed:
                        # finalize 결과 - 스트리밍이 없었을 때만 전송 (중복 방지)
                        yield {"type": "text", "content": text}

        logger.info("Streaming complete")

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield {"error": str(e), "message": "요청 처리 중 오류가 발생했습니다."}


# ==========================================================================
# 메인 (로컬 테스트용)
# ==========================================================================
if __name__ == "__main__":
    logger.info("Starting AgentCore Runtime...")
    app.run()
