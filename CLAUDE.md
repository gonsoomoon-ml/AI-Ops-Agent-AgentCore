# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Before taking any action, ask me for confirmation.**

## Project Overview

OpsAgent is an AI-powered operations agent with a **self-correcting evaluation system** built on [Strands Agents SDK](https://strandsagents.com/) and AWS Bedrock. It monitors CloudWatch/Datadog, detects problems, and validates responses through a 5-stage graph pipeline (ANALYZE → EVALUATE → DECIDE → FINALIZE/REGENERATE) that ensures quality before delivery. Supports both local CLI and AWS Bedrock AgentCore deployment.

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
uv run pytest tests/test_evaluation.py -k "cloudwatch" -v   # By keyword

# Linting & Type Checking
uv run ruff check src/ tests/ --fix    # Lint + auto-fix
uv run mypy src/ops_agent              # Type check (strict mode)

# AgentCore deployment
cd agentcore
./deploy_infra.sh                           # CloudFormation setup (IAM, SSM)
uv run python scripts/deploy.py --auto-update  # Deploy to AgentCore
uv run python scripts/invoke.py --interactive  # Test deployed agent
```

## Architecture

### Graph Workflow (enabled via `enable_evaluation=True`)

```
User Query → ANALYZE (Strands Agent + tools, async streaming)
           → EVALUATE (checkers score response 0.0-1.0)
           → DECIDE (≥0.7: PASS, 0.3-0.7: REGENERATE, <0.3: BLOCK)
           → FINALIZE or REGENERATE (retry with feedback, max 2x)
```

Nodes are defined in `graph/nodes.py`, conditions in `graph/conditions.py`, and the graph is compiled in `graph/runner.py` using Strands `GraphBuilder` with `max_node_executions=15`.

### Key Patterns

**Tool Factory** — tools are selected at runtime by `CLOUDWATCH_MODE` env var (mock/mcp). The factory in `tools/cloudwatch/__init__.py` lazily imports the appropriate module. New tool integrations (Datadog, KB) follow the same pattern.

**Global State Registry** — since Strands `FunctionNode` wrappers don't pass `invocation_state`, graph nodes access shared state via a thread-safe global registry in `graph/state.py`. Each workflow gets a unique ID; nodes call `get_current_workflow_state()` to read/write `OpsWorkflowState`.

**Message Injection** — for testing without real API calls, `OpsAgent.invoke_with_mock_history()` builds synthetic tool-use message history:
```python
mock_results = [{"tool_name": "cloudwatch_filter_log_events",
                 "tool_input": {"log_group_name": "/aws/lambda/payment"},
                 "tool_result": '{"events": [...]}'}]
response = agent.invoke_with_mock_history("분석해줘", mock_results)
```

**Prompt Caching** — Bedrock's `cachePoint` in `SystemContentBlock` caches system prompts + tool definitions across turns for up to 90% cost reduction. Enabled via `PROMPT_CACHE_ENABLED=true`.

**Singleton Settings** — `config/settings.py` uses Pydantic `BaseSettings` with `@lru_cache` singleton. Reads `.env` file + environment variables with case-insensitive aliases.

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| OpsAgent | `src/ops_agent/agent/ops_agent.py` | Main agent class, graph/simple mode factory |
| Graph Runner | `src/ops_agent/graph/runner.py` | Wraps Strands GraphBuilder, manages workflow |
| Graph Nodes | `src/ops_agent/graph/nodes.py` | ANALYZE, EVALUATE, DECIDE, FINALIZE, REGENERATE |
| Graph State | `src/ops_agent/graph/state.py` | OpsWorkflowState + thread-safe global registry |
| Evaluator | `src/ops_agent/evaluation/evaluator.py` | Orchestrates checkers, determines verdict |
| Checkers | `src/ops_agent/evaluation/checkers/` | BaseChecker interface + CloudWatchChecker |
| Eval Models | `src/ops_agent/evaluation/models.py` | ToolResult, CheckResult, EvalResult, EvalVerdict |
| Tools | `src/ops_agent/tools/cloudwatch/` | Factory: mock_tools.py or mcp_tools.py |
| Telemetry | `src/ops_agent/telemetry/setup.py` | Langfuse/OTEL observability setup |
| Settings | `src/ops_agent/config/settings.py` | Pydantic BaseSettings, `.env` loading |
| Prompts | `src/ops_agent/prompts/` | System prompts (Korean/English) via templates |
| AgentCore Entry | `agentcore/runtime/entrypoint.py` | BedrockAgentCoreApp streaming wrapper |

### Evaluation System

Checkers in `evaluation/checkers/` inherit `BaseChecker` and implement `check(response, tool_results) → CheckResult` scoring 0.0–1.0. The evaluator computes a weighted average then applies thresholds:

| Score | Verdict | Action |
|-------|---------|--------|
| ≥ 0.7 | PASS | Finalize and publish |
| 0.3–0.7 | REGENERATE | Retry with feedback (max 2 attempts) |
| < 0.3 | BLOCK | Finalize with quality warning |

### Async/Streaming

All graph nodes are async. `analyze_node` and `finalize_node` yield token deltas for real-time streaming. `OpsAgent.stream_async()` is the entry point for AgentCore, while `invoke()` is synchronous for local CLI.

## Configuration

Key environment variables (`.env`):
- `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_TEMPERATURE` (0.0 for consistency), `BEDROCK_MAX_TOKENS`
- `AGENT_LANGUAGE` (ko/en), `AGENT_LOG_LEVEL`
- `CLOUDWATCH_MODE`, `DATADOG_MODE`, `KB_MODE` — mock/mcp toggle per tool
- `PROMPT_CACHE_ENABLED` — Bedrock prompt caching

## Observability

- **Local (Strands)**: `STRANDS_OBSERVABILITY_MODE` = disabled | langfuse-public | langfuse-selfhosted
- **Production (AgentCore)**: `AGENTCORE_OBSERVABILITY_MODE` = disabled | langfuse-public | langfuse-selfhosted | native

See [docs/observability-langfuse.md](docs/observability-langfuse.md) for Langfuse API keys and setup.

## Dependencies

All dependencies are in `setup/pyproject.toml`. Use `uv sync` to install.

Key packages:
- `strands-agents[otel]` — Strands Agents SDK (agent framework + OTEL tracing)
- `mcp` — Model Context Protocol client
- `boto3` — AWS SDK (Bedrock, CloudWatch, S3, SSM, etc.)
- `pydantic-settings` — Settings management with `.env` support
- `opensearch-py` — OpenSearch Serverless client (Bedrock KB vector store)
- `retrying` — Retry decorator (KB creation with OpenSearch)
- `PyYAML` — YAML parsing (KB data files)
- `langfuse` — Observability tracing

```bash
uv sync                    # Install all dependencies
uv sync --extra dev        # Include dev dependencies (ruff, mypy, pytest-cov)
uv sync --extra datadog    # Include Datadog client
```

## Development Phases

- **Phase 1** ✅: CloudWatch + evaluation system + graph workflow
- **Phase 1.5** ✅: Langfuse observability integration
- **Phase 2** (Planned): Datadog integration — add tools in `tools/datadog/`, checker in `evaluation/checkers/`
- **Phase 3** (In Progress): Knowledge Base — Bedrock KB + OpenSearch Serverless for refrigerator Q&A data
