# 기술 리서치 결과

> 리서치 키워드 기반 조사 결과 정리
> 작성일: 2026-01-30

---

## 목차

1. [AIOps Agent Architecture Pattern](#1-aiops-agent-architecture-pattern)
2. [Strands Agent SDK Best Practices](#2-strands-agent-sdk-best-practices)
3. [MCP Server Production Pattern](#3-mcp-server-production-pattern)
4. [Bedrock AgentCore Deployment](#4-bedrock-agentcore-deployment)
5. [Multi-Tool Agent Orchestration](#5-multi-tool-agent-orchestration)
6. [참조 코드 분석 요약](#6-참조-코드-분석-요약)
7. [핵심 코드 패턴](#7-핵심-코드-패턴)

---

## 1. AIOps Agent Architecture Pattern

| 패턴명 | 적용 영역 | 참조 링크 |
|--------|----------|----------|
| **Agentic AIOps (Modular Agent Network)** | Task-specific agents (RCA, correlation, summarization) working in tandem | [LogicMonitor - Agentic AIOps](https://www.logicmonitor.com/blog/agent-driven-aiops-is-defining-future-of-it-operations) |
| **Three-Layer AIOps Stack** | Data ingestion → Analytics → Action layers | [TangoNet - AIOps Architecture](https://tangonetsolutions.com/aiops-architecture/) |
| **Google's 8 Multi-Agent Patterns** | Sequential pipelines, parallel execution, human-in-the-loop | [InfoQ - Multi-Agent Design Patterns](https://www.infoq.com/news/2026/01/multi-agent-design-patterns/) |
| **Microservices-style Agent Architecture** | Single-purpose agents replacing monolithic all-purpose agents | [Medium - Agentic AI Design Patterns 2026](https://medium.com/@dewasheesh.rana/agentic-ai-design-patterns-2026-ed-e3a5125162c5) |

### 핵심 인사이트

- **성능 지표**: MTTR 60-70% 감소, False positive 90% 이상 감소 가능
- **실패 원인**: 2024-2026 AI failures는 모델 품질이 아닌 아키텍처 문제에서 발생
- **권장 접근**: Single Agent + Multi-Tool이 Phase 1에 적합 (복잡도 낮음)

### AIOps 3-Layer 아키텍처

```
┌─────────────────────────────────────┐
│         Action Layer                │  ← 자동화된 대응, 알림, 티켓 생성
├─────────────────────────────────────┤
│         Analytics Layer             │  ← 패턴 분석, 상관관계, 리스크 탐지
├─────────────────────────────────────┤
│         Data Ingestion Layer        │  ← 텔레메트리 수집 및 정규화
└─────────────────────────────────────┘
```

### Agentic AIOps 특징

- **모듈러 설계**: 특화된 AI 에이전트들이 협력, 적응, 독립적 진화
- **태스크 특화**: RCA 에이전트, 알림 상관관계 에이전트, 요약 에이전트 등
- **플랫폼 독립**: 새 기능 추가시 전체 플랫폼 오버홀 불필요

---

## 2. Strands Agent SDK Best Practices

| 패턴명 | 적용 영역 | 참조 링크 |
|--------|----------|----------|
| **Model-Driven Agent Pattern** | LLM + System Prompt + Tools 3가지 핵심 컴포넌트 | [AWS Blog - Strands SDK Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/) |
| **Monolithic → Microservice Migration** | 단순 시작 후 필요시 tool 분리 | [Strands Agents Documentation](https://strandsagents.com/latest/) |
| **Role-Based Agent Factory** | YAML config로 역할별 모델 설정 | Local: `/home/ubuntu/explainable-translate-agent/config/models.yaml` |
| **Prompt Caching (90% 비용 절감)** | 동일 system prompt 재사용시 cache hit | Local: `/home/ubuntu/explainable-translate-agent/src/utils/strands_utils.py` |
| **Async Streaming + Retry Pattern** | `run_agent_async()` with exponential backoff | [GitHub - strands-agents/sdk-python](https://github.com/strands-agents/sdk-python) |
| **@tool Decorator Pattern** | Docstring 기반 tool schema 자동 생성 | Local: `/home/ubuntu/ec-customer-support-e2e-agentcore/src/agent.py` |

### Strands SDK 핵심 개념

```
┌─────────────────────────────────────────────┐
│              Strands Agent                  │
├─────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐ │
│  │   LLM   │  │ System  │  │    Tools    │ │
│  │ (Model) │  │ Prompt  │  │ (@tool)     │ │
│  └─────────┘  └─────────┘  └─────────────┘ │
│                    │                        │
│            Autonomous Reasoning             │
│         (도구 사용 시점/방법 자율 결정)       │
└─────────────────────────────────────────────┘
```

### 배포 전략

- **Monolithic**: Agent loop + 모든 tools가 하나의 프로세스
  - 장점: 단순, 낮은 latency (in-memory function call)
  - 적합: 초기 개발, 단순한 use case

- **Microservices**: 각 tool이 별도 서비스
  - 장점: 장애 격리, 독립적 스케일링, 다국어 구현 가능
  - 적합: 프로덕션, 복잡한 use case

### 보안 Best Practices

- Production 환경에서는 Resource를 특정 model ARN으로 scope down
- MAESTRO framework로 agentic AI 위협 모델링
- Input validation, output filtering, robust exception handling 필수

---

## 3. MCP Server Production Pattern

| 패턴명 | 적용 영역 | 참조 링크 |
|--------|----------|----------|
| **Remote MCP Server Pattern** | Production 환경에서 중앙집중식 tool 접근 | [Model Context Protocol Spec](https://modelcontextprotocol.io/specification/2025-11-25) |
| **Single-Purpose Server Pattern** | DB, Files, API 별도 서버 (monolithic 회피) | [MCP Best Practices](https://modelcontextprotocol.info/docs/best-practices/) |
| **OAuth Resource Server Pattern** | MCP 서버를 OAuth Resource Server로 분류 (June 2025 spec) | [Descope - MCP Explained](https://www.descope.com/learn/post/mcp) |
| **Human-in-the-Loop for Dangerous Actions** | 티켓 생성은 자동, 프로덕션 변경은 승인 필요 | [Vercel - MCP FAQ](https://vercel.com/blog/model-context-protocol-mcp-explained) |
| **Containerized Deployment** | Docker로 dev/staging/prod 일관성 보장 | [GitHub - MCP Servers](https://github.com/modelcontextprotocol/servers) |

### MCP 개요

- **정의**: LLM 애플리케이션과 외부 데이터 소스/도구 간의 통합을 위한 오픈 프로토콜
- **역사**: 2024년 11월 Anthropic 발표 → 2025년 3월 OpenAI 채택 → 2025년 12월 Linux Foundation 기부
- **SDK**: Python, TypeScript, C#, Java, Swift, Kotlin 공식 지원

### 아키텍처 패턴

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  MCP Client │────▶│  MCP Server │────▶│  External   │
│  (AI Model) │◀────│  (Gateway)  │◀────│  Service    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                    OAuth Resource
                       Server
```

### 보안 고려사항

| 항목 | 권장사항 |
|------|----------|
| **Secrets 관리** | Model context에 직접 노출 금지 → server-side에서 처리 |
| **Prompt Injection** | Tool calling을 policy-governed로 처리 |
| **권한 관리** | Over-permissioning 주의 (2,000+ 서버 취약점 발견) |
| **Human-in-the-Loop** | 위험 작업은 승인 필요, 티켓 생성 등은 자동 허용 |

---

## 4. Bedrock AgentCore Deployment

| 패턴명 | 적용 영역 | 참조 링크 |
|--------|----------|----------|
| **4-Line Runtime Pattern** | BedrockAgentCoreApp 최소 배포 구조 | Local: `/home/ubuntu/ec-customer-support-e2e-agentcore/src/helpers/lab4_runtime.py` |
| **Memory Hook Pattern** | `HookProvider`로 context injection & conversation save | Local: `/home/ubuntu/ec-customer-support-e2e-agentcore/src/helpers/ecommerce_memory.py` |
| **Message Injection Pattern** | Mock tool results로 실제 API 호출 없이 테스트 | Local: `/home/ubuntu/ec-customer-support-e2e-agentcore/under_development/messages_injection/` |
| **IAM Execution Role Pattern** | bedrock-agentcore.amazonaws.com trust policy | [AWS AgentCore Docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) |
| **MicroVM Session Isolation** | 각 사용자 세션별 dedicated microVM | [AWS Blog - AgentCore Intro](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/) |
| **SSM Parameter Storage** | Runtime config를 SSM에 저장 | Local: `/home/ubuntu/ec-customer-support-e2e-agentcore/src/helpers/utils.py` |

### AgentCore 구성 요소

```
┌─────────────────────────────────────────────────────────┐
│                 Amazon Bedrock AgentCore                │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Runtime   │  │   Memory    │  │  Observability  │ │
│  │ (Serverless │  │ (Session +  │  │ (Step-by-step   │ │
│  │  microVM)   │  │  Long-term) │  │  visualization) │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Supported Frameworks: CrewAI, LangGraph, LlamaIndex,   │
│                        Strands Agents                   │
└─────────────────────────────────────────────────────────┘
```

### 배포 방법

| 방법 | 설명 |
|------|------|
| **Starter Toolkit CLI** | `agentcore configure --entrypoint my_agent.py` |
| **AgentCore Python SDK** | 프로그래밍 방식 배포 |
| **AWS SDK** | boto3 직접 사용 |
| **IaC** | CloudFormation, CDK, Terraform |

### 인증 방식

| 방식 | 용도 | 특징 |
|------|------|------|
| **IAM/SigV4** | 내부 AWS 리소스 | boto3 credential resolution |
| **OAuth/JWT Bearer** | 외부 클라이언트 | Cognito, Okta 등 IdP 연동 |

---

## 5. Multi-Tool Agent Orchestration

| 패턴명 | 적용 영역 | 참조 링크 |
|--------|----------|----------|
| **ReAct Pattern** | Reasoning + Acting 반복 루프 | [IBM - LLM Agent Orchestration](https://www.ibm.com/think/tutorials/llm-agent-orchestration-with-langchain-and-granite) |
| **Sequential Agent Pattern** | output_key로 state 전달, 다음 agent가 이어받음 | [Google - Multi-Agent Patterns in ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/) |
| **Parallel Evaluation Pattern** | asyncio.gather()로 동시 평가 후 aggregation | Local: `/home/ubuntu/explainable-translate-agent/src/graph/nodes.py` |
| **GraphBuilder Workflow** | FunctionNode + conditional edges + execution limits | Local: `/home/ubuntu/explainable-translate-agent/src/graph/builder.py` |
| **Handoff Pattern** | 전문 agent로 task 위임 | [OpenAI - Orchestrating Multiple Agents](https://openai.github.io/openai-agents-python/multi_agent/) |
| **Human-in-the-Loop Pattern** | 위험 작업 전 사람 승인 | [Google - Multi-Agent Patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/) |
| **LangGraph (Fastest Framework)** | Graph 기반 state delta 전달로 최소 토큰 사용 | [ZenML - Best LLM Orchestration Frameworks](https://www.zenml.io/blog/best-llm-orchestration-frameworks) |

### 7가지 필수 디자인 패턴

1. **ReAct**: Reasoning + Acting 반복
2. **Reflection**: 자기 평가 및 개선
3. **Tool Use**: 외부 도구 활용
4. **Planning**: 작업 계획 수립
5. **Multi-Agent Collaboration**: 에이전트 간 협력
6. **Sequential Workflows**: 순차적 작업 흐름
7. **Human-in-the-Loop**: 사람 개입 지점

### Orchestration 요구사항

| 요구사항 | 설명 |
|----------|------|
| **Feedback Cycles** | 품질 평가에 따른 작업 반복 |
| **Conditional Routing** | 이전 결과에 따른 다음 action 결정 |
| **Mutable Shared State** | 다수 agent가 동일 context 읽기/수정 |
| **Durability** | 장애 시에도 시스템 유지 |

### 시장 동향

- **Gartner**: Multi-agent system 문의 1,445% 증가 (Q1 2024 → Q2 2025)
- **LangGraph**: 가장 빠르고 토큰 효율적 (필요한 state delta만 전달)
- **2026 트렌드**: AI가 진정한 agentic으로 진화 (reasoning + action + multi-tool)

---

## 6. 참조 코드 분석 요약

### 6.1 explainable-translate-agent (Strands Agent 패턴)

**저장소 위치**: `/home/ubuntu/explainable-translate-agent`

| 컴포넌트 | 파일 경로 | 패턴 설명 |
|----------|----------|----------|
| Agent Factory | `src/utils/strands_utils.py:347-434` | Role-based agent creation with caching |
| Agent Execution | `src/utils/strands_utils.py:618-660` | Async streaming + retry |
| Tool Definition | `src/tools/translator_tool.py` | Prompt build → agent → parse JSON |
| Prompt Templates | `src/prompts/template.py` | Markdown with YAML frontmatter + Jinja2 |
| System Prompts | `src/prompts/*.md` | Structured with XML sections |
| Data Models | `src/models/*.py` | Pydantic with Field constraints |
| Workflow | `src/graph/builder.py:86-156` | GraphBuilder with FunctionNode |
| Node Implementation | `src/graph/nodes.py` | Global state access pattern |
| State Management | `src/utils/workflow_state.py` | Thread-safe global registry |
| Observability | `src/utils/strands_utils.py:42-170` | OpenTelemetry context management |
| Token Tracking | `src/utils/strands_utils.py:733-1020` | TokenTracker for cost monitoring |

### 6.2 ec-customer-support-e2e-agentcore (AgentCore 배포 패턴)

**저장소 위치**: `/home/ubuntu/ec-customer-support-e2e-agentcore`

| 컴포넌트 | 파일 경로 | 패턴 설명 |
|----------|----------|----------|
| Runtime Entry | `src/helpers/lab4_runtime.py` | 4-line BedrockAgentCoreApp |
| Memory Hooks | `src/helpers/ecommerce_memory.py:13-116` | HookProvider with retrieve/save |
| Memory Strategies | `src/helpers/ecommerce_memory.py:148-214` | USER_PREFERENCE, SEMANTIC |
| Message Injection | `under_development/messages_injection/` | Fake history for testing |
| IAM Setup | `src/helpers/utils.py:245-423` | AgentCore execution role creation |
| SSM Parameters | `src/helpers/utils.py:19-46` | Configuration storage |
| Auth Patterns | `docs/agentcore-invocation-patterns.md` | IAM SigV4 vs OAuth JWT |
| Tool Definition | `src/agent.py:48-485` | @tool decorator with docstrings |

### 6.3 amazon-bedrock-agentcore-samples (AWS 공식 패턴)

**저장소 위치**: `/home/ubuntu/amazon-bedrock-agentcore-samples`

| 컴포넌트 | 파일 경로 | 패턴 설명 |
|----------|----------|----------|
| SDK Agent | `02-use-cases/AWS-operations-agent/agentcore-runtime/src/agents/sdk_agent.py` | Production-ready streaming pattern |
| Memory API | `02-use-cases/AWS-operations-agent/agentcore-runtime/src/agent_shared/memory.py` | get_last_k_turns, create_event |
| MCP Integration | `02-use-cases/AWS-operations-agent/mcp-tool-lambda/` | MCPClient with functools.partial |
| Tool Handler | `02-use-cases/AWS-operations-agent/mcp-tool-lambda/lambda/mcp-tool-handler.py` | Lambda-based tool execution |
| CloudFormation | `04-infrastructure-as-code/cloudformation/basic-runtime/template.yaml` | IaC deployment template |
| Gateway Utils | `01-tutorials/02-AgentCore-gateway/utils.py` | Gateway configuration |
| Memory Tutorials | `01-tutorials/04-AgentCore-memory/` | Memory strategy examples |
| SRE Agent | `02-use-cases/SRE-agent/` | Multi-agent orchestration for infra |

---

## 7. 핵심 코드 패턴

### 7.1 Agent Factory Pattern

```python
# Role-based agent creation with prompt caching
def get_agent(
    role: str,                          # Model role selector from YAML
    system_prompt: str,                 # System prompt content
    agent_name: Optional[str] = None,   # For logging
    prompt_cache: bool = True,          # Enable 90% cost reduction
    cache_type: str = "default",        # "default" or "ephemeral"
    tools: Optional[List] = None,       # Tool definitions
    streaming: bool = True,             # Streaming output
) -> Agent:
    """Creates Strands Agent with BedrockModel configuration"""

    config = load_config()  # From YAML
    model_config = config.models[role]

    model = BedrockModel(
        model_id=model_config.model_id,
        temperature=model_config.temperature,
        max_tokens=model_config.max_tokens,
        region_name=config.region
    )

    return Agent(
        model=model,
        tools=tools or [],
        system_prompt=system_prompt
    )
```

### 7.2 4-Line AgentCore Runtime Pattern

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

# Line 1: Create app
app = BedrockAgentCoreApp()

# Line 2 & 3: Define entrypoint
@app.entrypoint
def invoke(payload):
    user_input = payload.get("prompt", "")
    response = agent(user_input)
    return response.message["content"][0]["text"]

# Line 4: Run
if __name__ == "__main__":
    app.run()
```

### 7.3 Message Injection Pattern (Phase 1 Mock)

```python
# Simulate tool execution without actual API calls
fake_history = [
    # User message
    {"role": "user", "content": [{"text": "지난 1시간 API 에러율 조회해줘"}]},

    # Assistant with tool use
    {"role": "assistant", "content": [
        {"text": "API 에러율을 조회하겠습니다."},
        {"toolUse": {
            "toolUseId": "mock_001",
            "name": "datadog_get_metrics",
            "input": {
                "metric_name": "api.error_rate",
                "time_range": "1h"
            }
        }}
    ]},

    # Tool result (mocked)
    {"role": "user", "content": [
        {"toolResult": {
            "toolUseId": "mock_001",
            "status": "success",
            "content": [{"text": '{"error_rate": 2.3, "trend": "increasing"}'}]
        }}
    ]}
]

# Create agent with injected history
agent = Agent(
    model=model,
    tools=[datadog_get_metrics, cloudwatch_filter_logs],
    system_prompt=SYSTEM_PROMPT,
    messages=fake_history  # Key: Inject mock conversation
)

# Continue conversation - agent treats fake_history as real
response = agent("이 에러율이 정상 범위인가요?")
```

### 7.4 Tool Definition Pattern

```python
from strands.tools import tool

@tool
def datadog_get_metrics(
    metric_name: str,
    time_range: str = "1h",
    aggregation: str = "avg",
    filters: Optional[Dict[str, str]] = None
) -> str:
    """
    Query metrics from Datadog.

    Args:
        metric_name: Name of the metric (e.g., 'api.error_rate')
        time_range: Time range for query (e.g., '1h', '24h', '7d')
        aggregation: Aggregation method ('avg', 'sum', 'max', 'min')
        filters: Optional filters (e.g., {'service': 'payment'})

    Returns:
        JSON string with metric data and statistics
    """
    # Implementation here
    return json.dumps({"metric": metric_name, "value": 2.3})
```

### 7.5 Memory Hook Pattern

```python
from strands.hooks import AfterInvocationEvent, HookRegistry, MessageAddedEvent
from bedrock_agentcore.memory import MemoryClient

class OpsAgentMemoryHooks(HookProvider):
    def __init__(self, memory_id: str, client: MemoryClient,
                 actor_id: str, session_id: str):
        self.memory_id = memory_id
        self.client = client
        self.actor_id = actor_id
        self.session_id = session_id

    def retrieve_context(self, event: MessageAddedEvent):
        """Inject relevant context before LLM invocation"""
        messages = event.agent.messages
        if messages[-1]["role"] == "user":
            user_query = messages[-1]["content"][0]["text"]

            # Retrieve similar memories
            memories = self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace="ops/history",
                query=user_query,
                top_k=3
            )

            # Inject context
            if memories:
                context = "\n".join([m.get("content", {}).get("text", "")
                                    for m in memories])
                messages[-1]["content"][0]["text"] = f"""
이전 관련 내용:
{context}

현재 질문: {user_query}"""

    def save_interaction(self, event: AfterInvocationEvent):
        """Save conversation after response"""
        messages = event.agent.messages
        if len(messages) >= 2 and messages[-1]["role"] == "assistant":
            # Extract and save
            self.client.create_event(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                messages=[
                    (user_query, "USER"),
                    (assistant_response, "ASSISTANT")
                ]
            )

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(MessageAddedEvent, self.retrieve_context)
        registry.add_callback(AfterInvocationEvent, self.save_interaction)
```

### 7.6 Parallel Evaluation Pattern

```python
import asyncio

async def evaluate_incident(incident_data: Dict) -> Dict:
    """Run multiple evaluators in parallel"""

    results = await asyncio.gather(
        analyze_metrics(incident_data),
        analyze_logs(incident_data),
        search_knowledge_base(incident_data)
    )

    metrics_result, logs_result, kb_result = results

    # Aggregate results (deterministic SOP, not LLM)
    return {
        "metrics_analysis": metrics_result,
        "logs_analysis": logs_result,
        "kb_recommendations": kb_result,
        "severity": calculate_severity(results),
        "recommended_actions": prioritize_actions(results)
    }
```

---

## 부록: 프로젝트 적용 권장사항

### Phase 1 (Mock 기반)

| 항목 | 권장 패턴 | 출처 |
|------|----------|------|
| Agent 구조 | Single Agent + Multi-Tool | AIOps 리서치 |
| Mock 테스트 | Message Injection Pattern | ec-customer-support |
| Tool 정의 | @tool decorator + Pydantic | Strands SDK |
| 프롬프트 | Markdown + YAML frontmatter | explainable-translate |

### Phase 2 (실제 연동)

| 항목 | 권장 패턴 | 출처 |
|------|----------|------|
| Datadog 연동 | MCP Server Pattern | MCP Spec |
| CloudWatch 연동 | boto3 직접 호출 | AWS SDK |
| Knowledge Base | Bedrock KB API | AgentCore Samples |
| 에러 처리 | Exponential backoff retry | Strands Utils |

### Phase 3 (AgentCore 배포)

| 항목 | 권장 패턴 | 출처 |
|------|----------|------|
| Runtime | 4-Line Pattern | ec-customer-support |
| Memory | Hook Pattern | ecommerce_memory.py |
| 인증 | OAuth JWT | agentcore-invocation-patterns |
| IaC | CloudFormation | agentcore-samples |
| 모니터링 | OpenTelemetry | Strands observability |

---

## 부록: 추가 참조 링크

### System Prompt 구성 참조

| 프로젝트 | 설명 | 링크 |
|----------|------|------|
| Self-Correcting-Explainable-Translation-Agent | YAML frontmatter + Jinja2 템플릿 패턴 | [GitHub - prompts](https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent/tree/main/01_explainable_translate_agent/src/prompts) |
| sample-deep-insight | XML 태그 기반 섹션 구조 + 역할별 프롬프트 | [GitHub - prompts](https://github.com/aws-samples/sample-deep-insight/tree/main/self-hosted/src/prompts) |

### Agent Tool 구현 참조

| 프로젝트 | 설명 | 링크 |
|----------|------|------|
| sample-deep-insight | @log_io 데코레이터, Colors 클래스, TOOL_SPEC 패턴 | [GitHub - tools](https://github.com/aws-samples/sample-deep-insight/tree/main/self-hosted/src/tools) |

### Strands Agent Graph 구현 참조

| 프로젝트 | 설명 | 링크 |
|----------|------|------|
| Self-Correcting-Explainable-Translation-Agent | GraphBuilder, FunctionNode, conditional edges 패턴 | [GitHub - graph](https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent/tree/main/01_explainable_translate_agent/src/graph) |

### Bedrock AgentCore 구현 참조

| 프로젝트 | 설명 | 링크 |
|----------|------|------|
| ec-customer-support-e2e-agentcore | AgentCore Observability (트레이싱, 모니터링) | [Notebook - lab-05](https://github.com/gonsoomoon-ml/ec-customer-support-e2e-agentcore/blob/main/notebooks/lab-05-agentcore-observability/lab-05-agentcore-observability.ipynb) |
| sample-deep-insight (managed-agentcore) | VPC 내 AgentCore Runtime 생성 | [01_create_agentcore_runtime_vpc.py](https://github.com/aws-samples/sample-deep-insight/blob/main/managed-agentcore/01_create_agentcore_runtime_vpc.py) |
| sample-deep-insight (managed-agentcore) | VPC 내 AgentCore Runtime 호출 | [02_invoke_agentcore_runtime_vpc.py](https://github.com/aws-samples/sample-deep-insight/blob/main/managed-agentcore/02_invoke_agentcore_runtime_vpc.py) |

### 주요 파일 참조

| 파일 | 패턴 | 링크 |
|------|------|------|
| `coder.md` | 역할별 프롬프트 구조 (Role, Behavior, Instructions, Output Format, Constraints) | [coder.md](https://github.com/aws-samples/sample-deep-insight/blob/main/self-hosted/src/prompts/coder.md) |
| `template.py` | 프롬프트 템플릿 로더 (PromptTemplate, PromptTemplateLoader) | [template.py](https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent/blob/main/01_explainable_translate_agent/src/prompts/template.py) |
| `bash_tool.py` | Tool 구현 패턴 (TOOL_SPEC, @log_io, PythonAgentTool) | [bash_tool.py](https://github.com/aws-samples/sample-deep-insight/blob/main/self-hosted/src/tools/bash_tool.py) |
| `decorators.py` | 로깅 데코레이터 패턴 | [decorators.py](https://github.com/aws-samples/sample-deep-insight/blob/main/self-hosted/src/tools/decorators.py) |

---

*이 문서는 Ops AI Agent 프로젝트의 기술 리서치 결과를 정리한 것입니다.*
