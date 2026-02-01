# Ops AI Agent - Project Specification

## Project Overview

AI-powered operations automation agent for monitoring, problem detection, and automated response using AWS CloudWatch and Datadog integrations, deployed on Amazon Bedrock AgentCore.

## Tech Stack

- **Framework**: Strands Agent SDK
- **Runtime**: Amazon Bedrock AgentCore
- **Memory**: Amazon Bedrock AgentCore Memory
- **RAG**: Amazon Bedrock Knowledge Base
- **Tools**: Datadog MCP, AWS CloudWatch API
- **Language**: Python 3.11+

## Architecture Decision

**Single Agent + Multi-Tool** (recommended for Phase 1)

| Factor | Single Agent + Multi-Tool | Multi-Agent |
|--------|---------------------------|-------------|
| Complexity | Lower | Higher |
| Latency | Lower (direct tool calls) | Higher (inter-agent overhead) |
| Phase 1 Mock | Easy (message injection) | Complex |

## Core Tools

### Datadog Tools
- `datadog_get_metrics(metric_name, time_range, aggregation, filters)`
- `datadog_get_service_logs(service_name, time_range, log_level)`
- `datadog_list_incidents(status, severity)`
- `datadog_list_monitors(name_filter, tags, status)`

### CloudWatch Tools
- `cloudwatch_get_metric_data(namespace, metric_name, dimensions, time_range)`
- `cloudwatch_filter_log_events(log_group_name, time_range, filter_pattern)`
- `cloudwatch_get_log_groups(prefix)`

### Knowledge Base Tools
- `kb_retrieve(query, max_results, min_score)`
- `kb_retrieve_and_generate(query, context, max_sources)`

## Implementation Phases

### Phase 1: Mock-Based Agent
- Message injection for tool simulation
- System prompt design (Korean/English)
- Test all 5 user scenarios

### Phase 2: Real Tool Integration
- Datadog MCP, CloudWatch boto3, Bedrock KB
- Error handling & retries

### Phase 3: AgentCore Deployment
- Memory API, containerization, IAM setup

## User Scenarios (Test Cases)

```
1. "지난 1시간 동안 API 에러율이 어떻게 됐어?" → Datadog metrics
2. "payment-service에서 500 에러 로그 보여줘" → CloudWatch logs
3. "이 에러 해결 방법이 사내 문서에 있어?" → Knowledge Base RAG
4. "현재 열린 인시던트 있어?" → Datadog incidents
5. "에러 원인 분석하고 조치 방안 추천해줘" → Multi-tool + reasoning
```

## Key Patterns (from Research)

### 1. Message Injection (Phase 1 Mock)
```python
fake_history = [
    {"role": "user", "content": [{"text": "user query"}]},
    {"role": "assistant", "content": [{"toolUse": {"toolUseId": "mock_001", "name": "tool_name", "input": {...}}}]},
    {"role": "user", "content": [{"toolResult": {"toolUseId": "mock_001", "content": [{"text": "mock result"}], "status": "success"}}]}
]
agent = Agent(model=model, tools=tools, messages=fake_history)
```

### 2. 4-Line AgentCore Runtime
```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload):
    return agent(payload.get("prompt", "")).message["content"][0]["text"]

if __name__ == "__main__":
    app.run()
```

### 3. Tool Definition
```python
from strands.tools import tool

@tool
def datadog_get_metrics(metric_name: str, time_range: str = "1h") -> str:
    """Query metrics from Datadog."""
    return json.dumps({"metric": metric_name, "value": 2.3})
```

## Reference Code

| Pattern | Location |
|---------|----------|
| Agent Factory + Caching | `/home/ubuntu/explainable-translate-agent/src/utils/strands_utils.py` |
| Message Injection | `/home/ubuntu/ec-customer-support-e2e-agentcore/under_development/messages_injection/` |
| Memory Hooks | `/home/ubuntu/ec-customer-support-e2e-agentcore/src/helpers/ecommerce_memory.py` |
| AgentCore Samples | `/home/ubuntu/amazon-bedrock-agentcore-samples/02-use-cases/` |

## Research Documentation

Full research results: [docs/research-guide-results.md](docs/research-guide-results.md)

## Work Guidelines

- **IMPORTANT: Before any action, ask the user for approval first**
- **Ask me before next step**
- **Write docstring and comment in Korean-friendly**
- Do not proceed with implementation without explicit user confirmation
- Test code first before user verification
- Phase 1: Use message injection for tool simulation
- Reference repos are for pattern reference only (no code copying)
