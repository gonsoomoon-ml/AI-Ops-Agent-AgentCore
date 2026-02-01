"""AgentCore 스크립트 유틸리티.

재사용 가능한 클래스와 함수를 제공합니다:
- Metrics: 스트리밍 성능 메트릭
- SSEParser: Server-Sent Events 파서
- AgentCoreClient: AgentCore Runtime 클라이언트
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agent_runtime import BedrockAgentRuntimeClient


# =============================================================================
# Metrics
# =============================================================================


@dataclass
class Metrics:
    """스트리밍 메트릭.

    Attributes:
        start: 시작 시간
        first_token: 첫 토큰 수신 시간
        end: 종료 시간
        tokens: 토큰 수
    """

    start: float = field(default_factory=time.time)
    first_token: float | None = None
    end: float | None = None
    tokens: int = 0

    def record_token(self) -> None:
        """토큰 수신 기록."""
        now = time.time()
        if self.first_token is None:
            self.first_token = now
        self.tokens += 1

    def finish(self) -> None:
        """종료 기록."""
        self.end = time.time()

    @property
    def ttft(self) -> float:
        """Time to First Token (초)."""
        return (self.first_token or self.start) - self.start

    @property
    def total(self) -> float:
        """총 소요 시간 (초)."""
        return (self.end or time.time()) - self.start

    @property
    def tps(self) -> float:
        """Tokens per second."""
        duration = self.total
        return self.tokens / duration if duration > 0 else 0

    def __str__(self) -> str:
        return f"TTFT: {self.ttft:.2f}s | Total: {self.total:.2f}s | Tokens: {self.tokens} | TPS: {self.tps:.1f}"


# =============================================================================
# SSE Parser
# =============================================================================


class SSEParser:
    """Buffer-based SSE 파서.

    Server-Sent Events 형식의 스트림을 파싱합니다.
    청크가 불완전하게 도착해도 버퍼링하여 올바르게 처리합니다.

    Example:
        parser = SSEParser()
        for chunk in stream:
            for text in parser.feed(chunk):
                print(text, end="")
        for text in parser.flush():
            print(text, end="")
    """

    DELIMITER = "\n\n"

    def __init__(self) -> None:
        self._buffer = ""
        self._seen: set[str] = set()  # 중복 제거용

    def feed(self, chunk: str) -> Generator[str, None, None]:
        """청크 파싱 후 텍스트 yield.

        Args:
            chunk: SSE 청크 문자열

        Yields:
            추출된 텍스트 콘텐츠
        """
        self._buffer += chunk

        while self.DELIMITER in self._buffer:
            event_str, self._buffer = self._buffer.split(self.DELIMITER, 1)
            text = self._extract_text(event_str)
            if text and text not in self._seen:
                self._seen.add(text)
                yield text

    def flush(self) -> Generator[str, None, None]:
        """남은 버퍼 처리.

        Yields:
            추출된 텍스트 콘텐츠
        """
        if self._buffer.strip():
            text = self._extract_text(self._buffer)
            if text and text not in self._seen:
                yield text
        self._buffer = ""
        self._seen.clear()

    def _extract_text(self, event_str: str) -> str | None:
        """SSE 이벤트에서 텍스트 추출.

        지원 형식:
            - data: {"type": "delta", "content": "..."}
            - data: {"type": "text", "content": "..."}

        Args:
            event_str: SSE 이벤트 문자열

        Returns:
            추출된 텍스트 또는 None
        """
        # data: 프리픽스 추출
        data = ""
        for line in event_str.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data += line[6:] if line.startswith("data: ") else line[5:]

        if not data:
            return None

        try:
            obj = json.loads(data)
            if obj.get("type") in ("delta", "text"):
                return obj.get("content")
        except json.JSONDecodeError:
            pass

        return None


# =============================================================================
# AgentCore Client
# =============================================================================


class AgentCoreClient:
    """AgentCore Runtime 클라이언트.

    AgentCore Runtime에 배포된 에이전트를 호출합니다.

    Example:
        client = AgentCoreClient(arn, region)
        for token in client.stream("Hello"):
            print(token, end="")
    """

    def __init__(self, arn: str, region: str) -> None:
        """클라이언트 초기화.

        Args:
            arn: AgentCore Runtime ARN
            region: AWS 리전
        """
        self.arn = arn
        self.region = region
        self._client: BedrockAgentRuntimeClient | None = None

    @property
    def client(self) -> BedrockAgentRuntimeClient:
        """Lazy-initialized boto3 클라이언트."""
        if self._client is None:
            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                config=Config(read_timeout=900, connect_timeout=60, retries={"max_attempts": 3}),
            )
        return self._client

    def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        raw: bool = False,
    ) -> Generator[str, None, None]:
        """스트리밍 호출.

        Args:
            prompt: 사용자 프롬프트
            session_id: 세션 ID (없으면 자동 생성)
            raw: True면 원시 청크 반환

        Yields:
            텍스트 토큰 또는 원시 청크

        Raises:
            RuntimeError: API 호출 실패 시
        """
        session_id = session_id or str(uuid.uuid4())

        try:
            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.arn,
                runtimeSessionId=session_id,
                payload=json.dumps({"prompt": prompt}),
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            if code == "ResourceNotFoundException":
                raise RuntimeError(f"에이전트 없음: {self.arn}") from e
            if code == "AccessDeniedException":
                raise RuntimeError("접근 거부") from e
            raise RuntimeError(f"호출 실패: {msg}") from e

        if "response" not in response:
            return

        parser = SSEParser()

        for event in response["response"]:
            chunk = self._decode(event)

            if raw:
                yield chunk
            else:
                yield from parser.feed(chunk)

        if not raw:
            yield from parser.flush()

    def _decode(self, event: dict | bytes) -> str:
        """이벤트 디코딩.

        Args:
            event: 원시 이벤트

        Returns:
            디코딩된 문자열
        """
        if isinstance(event, dict):
            if "chunk" in event and "bytes" in event["chunk"]:
                return event["chunk"]["bytes"].decode("utf-8")
            if "text" in event:
                return event["text"]
            return json.dumps(event, ensure_ascii=False)
        if isinstance(event, bytes):
            return event.decode("utf-8", errors="replace")
        return str(event)
