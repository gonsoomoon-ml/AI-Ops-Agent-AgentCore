# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpsAgent is an AI-powered operations agent with a **self-correcting evaluation system**. It monitors CloudWatch/Datadog, detects problems, and provides validated responses through a 5-stage pipeline (ANALYZE → EVALUATE → DECIDE → FINALIZE/REGENERATE) that ensures quality before delivery.

## Common Commands

```bash
# Setup
./setup/create_env.sh              # Initialize environment (uv + dependencies)
cp .env.example .env               # Create config file

# Run locally
uv run ops-agent                   # Interactive CLI chat
uv run python -m ops_agent.main --prompt "payment-service 에러 로그 보여줘"

# Testing
uv run pytest tests/ -v            # All tests
uv run pytest tests/test_evaluation.py -v                    # Single file
uv run pytest tests/test_evaluation.py -k "cloudwatch" -v   # By name

# Linting & Type Checking
uv run ruff check src/ tests/ --fix    # Lint + auto-fix
uv run mypy src/ops_agent              # Type check (strict)

# AgentCore deployment
cd agentcore
./deploy_infra.sh                           # CloudFormation setup
uv run python scripts/deploy.py --auto-update  # Deploy
uv run python scripts/invoke.py --interactive  # Test
```

## Architecture

### Graph Workflow (enabled via `enable_evaluation=True`)

```
User Query → ANALYZE (Strands Agent + tools)
           → EVALUATE (checkers score response 0.0-1.0)
           → DECIDE (≥0.7: PASS, 0.3-0.7: REGENERATE, <0.3: BLOCK)
           → FINALIZE or REGENERATE (retry with feedback, max 2x)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| OpsAgent | `src/ops_agent/agent/ops_agent.py` | Main agent class, graph/simple mode factory |
| Graph Runner | `src/ops_agent/graph/runner.py` | Wraps Strands GraphBuilder, manages workflow |
| Graph Nodes | `src/ops_agent/graph/nodes.py` | ANALYZE, EVALUATE, DECIDE, FINALIZE, REGENERATE |
| Evaluator | `src/ops_agent/evaluation/evaluator.py` | Orchestrates checkers, determines verdict |
| Checkers | `src/ops_agent/evaluation/checkers/` | BaseChecker + CloudWatchChecker |
| Tools | `src/ops_agent/tools/cloudwatch/tools.py` | `@tool` decorated functions |
| Telemetry | `src/ops_agent/telemetry/setup.py` | Langfuse/OTEL observability setup |
| Settings | `src/ops_agent/config/settings.py` | Pydantic BaseSettings, `.env` loading |
| Prompts | `src/ops_agent/prompts/` | System prompts (Korean/English) |

### Strands Agent Patterns

**Tool Declaration**:
```python
from strands import tool

@tool
def cloudwatch_filter_log_events(log_group_name: str, ...) -> str:
    """Filter CloudWatch logs."""
    if settings.is_cloudwatch_mock:
        return MOCK_DATA
    # Real boto3 call
```

**Message Injection** (for testing without real API calls):
```python
def invoke_with_mock_history(self, prompt: str, mock_tool_results: list[dict]):
    messages = self._build_mock_messages(mock_tool_results)
    agent = self._create_agent(messages=messages)
    return agent(prompt)
```

## Configuration

Key environment variables (`.env`):
- `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_TEMPERATURE`, `BEDROCK_MAX_TOKENS`
- `AGENT_LANGUAGE` (ko/en), `AGENT_LOG_LEVEL`
- `CLOUDWATCH_MODE`, `DATADOG_MODE`, `KB_MODE` (mock/mcp toggle)

## Observability (Langfuse Integration)

OpsAgent supports 5 observability modes for Strands (local) and AgentCore (production):

| # | Environment | Mode | Backend |
|---|-------------|------|---------|
| 1 | Strands | `langfuse-public` | Langfuse Cloud |
| 2 | Strands | `langfuse-selfhosted` | Self-hosted Langfuse |
| 3 | AgentCore | `langfuse-public` | Langfuse Cloud |
| 4 | AgentCore | `langfuse-selfhosted` | Self-hosted Langfuse |
| 5 | AgentCore | `native` | AWS ADOT (CloudWatch/X-Ray) |

### Environment Variables

```bash
# Strands (local development)
STRANDS_OBSERVABILITY_MODE=disabled    # disabled | langfuse-public | langfuse-selfhosted

# AgentCore (production)
AGENTCORE_OBSERVABILITY_MODE=disabled  # disabled | langfuse-public | langfuse-selfhosted | native

# Langfuse Public Cloud
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_PUBLIC_ENDPOINT=https://us.cloud.langfuse.com

# Langfuse Self-hosted
LANGFUSE_SELFHOSTED_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SELFHOSTED_SECRET_KEY=sk-lf-xxx
LANGFUSE_SELFHOSTED_ENDPOINT=http://your-alb.region.elb.amazonaws.com
```

### Usage

```python
# Strands local - auto-setup on OpsAgent init
from ops_agent.agent import OpsAgent
agent = OpsAgent(session_id="my-session", user_id="user@example.com")

# AgentCore deployment - pass env vars to runtime
from ops_agent.telemetry import get_agentcore_observability_env_vars
env_vars = get_agentcore_observability_env_vars()
runtime.launch(env_vars=env_vars)
```

See [docs/observability-langfuse.md](docs/observability-langfuse.md) for full documentation.

## Development Phases

- **Phase 1** (Complete): CloudWatch + evaluation system + graph workflow
- **Phase 1.5** (Complete): Langfuse observability integration
- **Phase 2** (Planned): Datadog integration
- **Phase 3** (Planned): Knowledge Base + AgentCore Memory
