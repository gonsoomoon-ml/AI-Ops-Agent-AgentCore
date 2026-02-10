# Streaming Implementation

OpsAgent의 실시간 스트리밍 구현 문서입니다.

## 아키텍처 개요

```
┌─────────────┐     ┌─────────────────┐     ┌───────────┐     ┌─────────┐     ┌─────────┐
│  invoke.py  │ ──▶ │  entrypoint.py  │ ──▶ │ OpsAgent  │ ──▶ │  Graph  │ ──▶ │ Bedrock │
│  (Client)   │     │   (Runtime)     │     │           │     │         │     │   API   │
└─────────────┘     └─────────────────┘     └───────────┘     └─────────┘     └─────────┘
      │                     │                     │                │               │
      │◀── SSE Events ──────│◀── dict Events ─────│◀── Events ─────│◀── Tokens ────│
```

## 스트리밍 흐름

### 1. Client → Runtime (SSE)

클라이언트(`invoke.py`)가 AgentCore Runtime을 호출하면, Server-Sent Events(SSE) 형식으로 응답을 받습니다.

```python
# invoke.py
for event in response["response"]:
    chunk = event["chunk"]["bytes"].decode("utf-8")
    # SSE 형식: "data: {\"type\": \"delta\", \"content\": \"Hello\"}\n\n"
```

### 2. Runtime → OpsAgent (dict)

Runtime(`entrypoint.py`)은 OpsAgent의 `stream_async()`를 호출하고, 텍스트를 추출하여 dict 형식으로 yield합니다.

```python
# entrypoint.py
async for event in agent.stream_async(prompt):
    text, is_delta = StreamingEventExtractor.extract(event)
    if text:
        yield {"type": "delta", "content": text}
```

### 3. OpsAgent → Graph (Events)

OpsAgent는 Graph의 `stream_async()`를 호출합니다.

```python
# ops_agent.py
async for event in self._graph.stream_async(prompt):
    yield event
```

### 4. Graph → Strands Agent → Bedrock (Tokens)

Graph의 `analyze_node`에서 Strands Agent를 호출하여 Bedrock API로부터 토큰을 스트리밍합니다.

```python
# nodes.py (analyze_node)
agent = _create_agent()
async for event in agent.stream_async(current_prompt):
    yield event
```

## 주요 파일

### Client Side

| 파일 | 설명 |
|------|------|
| `agentcore/scripts/invoke.py` | CLI 클라이언트, SSE 파싱 |
| `agentcore/scripts/util.py` | Metrics, SSEParser, AgentCoreClient |

### Runtime Side

| 파일 | 설명 |
|------|------|
| `agentcore/runtime/entrypoint.py` | AgentCore Runtime 진입점, 이벤트 추출 |

### Agent Side

| 파일 | 설명 |
|------|------|
| `src/ops_agent/agent/ops_agent.py` | OpsAgent 클래스, `stream_async()` |
| `src/ops_agent/graph/runner.py` | Graph 실행기, `stream_async()` |
| `src/ops_agent/graph/nodes.py` | 노드 구현, `analyze_node` (스트리밍) |
| `src/ops_agent/graph/function_node.py` | FunctionNode 래퍼, async generator 지원 |
| `src/ops_agent/graph/util.py` | 공통 유틸리티 |

## 이벤트 구조

### Graph 스트리밍 이벤트

Graph에서 발생하는 스트리밍 이벤트는 두 가지 형태입니다:

**형태 1 - 중첩 구조:**
```json
{
    "type": "multiagent_node_stream",
    "node_id": "analyze",
    "event": {
        "event": {
            "contentBlockDelta": {
                "delta": { "text": "Hello" }
            }
        }
    }
}
```

**형태 2 - 직접 delta 구조:**
```json
{
    "type": "multiagent_node_stream",
    "node_id": "analyze",
    "event": {
        "delta": { "text": "Hello" }
    }
}
```

### SSE 이벤트 (Client)

클라이언트가 받는 SSE 이벤트:

```
data: {"type": "delta", "content": "Hello"}

data: {"type": "delta", "content": " World"}

data: {"type": "text", "content": "Full response..."}
```

## 핵심 클래스

### StreamingEventExtractor (entrypoint.py)

Graph 이벤트에서 텍스트를 추출합니다.

```python
class StreamingEventExtractor:
    @staticmethod
    def extract(event: dict) -> tuple[str | None, bool]:
        """
        Returns:
            (텍스트, is_delta) - 텍스트가 없으면 (None, False)
        """
```

### SSEParser (scripts/util.py)

SSE 스트림을 파싱합니다.

```python
class SSEParser:
    def feed(self, chunk: str) -> Generator[str, None, None]:
        """청크를 파싱하여 텍스트 yield"""

    def flush(self) -> Generator[str, None, None]:
        """남은 버퍼 처리"""
```

### Metrics (scripts/util.py)

스트리밍 성능 메트릭을 추적합니다.

```python
@dataclass
class Metrics:
    start: float          # 시작 시간
    first_token: float    # 첫 토큰 시간
    tokens: int           # 토큰 수

    @property
    def ttft(self) -> float:
        """Time to First Token (초)"""

    @property
    def tps(self) -> float:
        """Tokens per second"""
```

### FunctionNode (function_node.py)

Python 함수를 Graph 노드로 래핑합니다.

```python
class FunctionNode(MultiAgentBase):
    async def stream_async(self, task=None, **kwargs):
        """
        async generator 함수면 이벤트를 yield
        일반 함수면 invoke_async로 폴백
        """
```

## 사용법

### 기본 테스트

```bash
# 단일 프롬프트
uv run python scripts/invoke.py --prompt "안녕하세요"

# 테스트 프롬프트
uv run python scripts/invoke.py --test simple

# 토큰별 타이밍
uv run python scripts/invoke.py --test simple --verbose

# 원시 이벤트 (디버깅)
uv run python scripts/invoke.py --test simple --raw

# 대화형 모드
uv run python scripts/invoke.py --interactive
```

### 출력 예시

```
======================================================================
AGENT RESPONSE
======================================================================

안녕하세요! 운영 자동화 AI 에이전트입니다...

----------------------------------------------------------------------
Session: 9fb2ae8e-8483-458f-a645-f2ad251fb2a0
Metrics: TTFT: 11.44s | Total: 13.60s | Tokens: 62 | TPS: 4.6
======================================================================
```

## 중복 방지

스트리밍 델타와 finalize 결과가 모두 전송되면 중복이 발생합니다. 이를 방지하기 위해:

```python
# entrypoint.py
has_streamed = False

async for event in agent.stream_async(prompt):
    text, is_delta = StreamingEventExtractor.extract(event)
    if text:
        if is_delta:
            has_streamed = True
            yield {"type": "delta", "content": text}
        elif not has_streamed:
            # finalize 결과 - 스트리밍이 없었을 때만 전송
            yield {"type": "text", "content": text}
```

## 성능 고려사항

### AWS 네트워크 배칭

AWS AgentCore는 네트워크 레벨에서 여러 토큰을 배치하여 전송합니다. 따라서 토큰이 개별적으로 도착하지 않고 ~10개씩 묶여서 도착할 수 있습니다.

```
[실제 동작]
토큰1, 토큰2, 토큰3... → 배치 → "토큰1토큰2토큰3..." (한 번에 도착)
```

### TTFT (Time to First Token)

첫 토큰까지의 시간은 다음 요소에 영향을 받습니다:
- Bedrock API 콜드 스타트
- Graph 워크플로우 초기화
- 네트워크 레이턴시

일반적으로 2-5초 정도 소요됩니다.

## 디버깅

### 원시 이벤트 확인

```bash
uv run python scripts/invoke.py --test simple --raw
```

### Runtime 로그 확인

```bash
aws logs tail /aws/bedrock-agentcore/runtimes/ops_ai_agent-EgxPs5Arss-DEFAULT \
  --log-stream-name-prefix "2026/02/01/[runtime-logs]" \
  --follow
```

### 로컬 테스트

```python
import asyncio
from ops_agent.agent import OpsAgent

async def test():
    agent = OpsAgent(enable_evaluation=True)
    async for event in agent.stream_async("안녕"):
        print(event)

asyncio.run(test())
```
