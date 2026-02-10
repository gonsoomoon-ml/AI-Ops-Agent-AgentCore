# OpsAgent Graph Workflow

Graph 기반 워크플로우 설계 및 구현 문서.

## 1. Overview

OpsAgent는 Self-Correcting 패턴을 구현한 Graph 기반 워크플로우를 사용합니다.
LLM 응답의 품질을 평가하고, 품질이 낮으면 자동으로 재생성합니다.

```
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
```

## 2. Workflow State

모든 노드가 공유하는 상태 객체입니다.

### 2.1 State Structure

```python
@dataclass
class OpsWorkflowState:
    # ===== Input =====
    prompt: str                    # 사용자 질문

    # ===== Agent Execution =====
    response: str | None           # LLM 응답
    tool_results: list[ToolResult] # 도구 실행 결과

    # ===== Evaluation =====
    eval_result: EvalResult | None # 평가 결과
    check_results: list[CheckResult] # 개별 검사 결과

    # ===== Decision =====
    verdict: EvalVerdict | None    # PASS / REGENERATE / BLOCK
    feedback: str | None           # 재생성 피드백

    # ===== Control =====
    attempt: int = 0               # 현재 시도 (0-indexed)
    max_attempts: int = 2          # 최대 시도 횟수

    # ===== Output =====
    final_response: str | None     # 최종 응답
    final_status: WorkflowStatus   # PENDING/PUBLISHED/REJECTED/ERROR

    # ===== Error =====
    error: str | None              # 오류 메시지

    # ===== Metadata =====
    metadata: dict[str, Any] = field(default_factory=dict)  # 추가 메타데이터
```

### 2.2 State Lifecycle

```
create_workflow_state()
        │
        ▼
┌─────────────────────────────────────────┐
│         OpsWorkflowState                │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ ANALYZE node updates:             │  │
│  │   state.response = "..."          │  │
│  │   state.tool_results = [...]      │  │
│  └───────────────────────────────────┘  │
│                  │                      │
│                  ▼                      │
│  ┌───────────────────────────────────┐  │
│  │ EVALUATE node updates:            │  │
│  │   state.eval_result = EvalResult  │  │
│  │   state.check_results = [...]     │  │
│  └───────────────────────────────────┘  │
│                  │                      │
│                  ▼                      │
│  ┌───────────────────────────────────┐  │
│  │ DECIDE node updates:              │  │
│  │   state.verdict = PASS/REGEN/BLOCK│  │
│  └───────────────────────────────────┘  │
│                  │                      │
│        ┌────────┴────────┐              │
│        ▼                 ▼              │
│  ┌────────────┐   ┌────────────────┐   │
│  │ REGENERATE │   │    FINALIZE    │   │
│  │            │   │                │   │
│  │ feedback++ │   │ final_response │   │
│  │ attempt++  │   │ final_status   │   │
│  │ reset()    │   └────────────────┘   │
│  └────────────┘                        │
│        │                               │
│        └──► Back to ANALYZE            │
│                                         │
└─────────────────────────────────────────┘
        │
        ▼
delete_workflow_state()
```

### 2.3 WorkflowStatus Enum

```python
class WorkflowStatus(Enum):
    PENDING = "pending"      # 초기 상태
    PUBLISHED = "published"  # 정상 완료 (PASS)
    REJECTED = "rejected"    # 품질 미달 (BLOCK)
    ERROR = "error"          # 오류 발생
```

### 2.4 EvalVerdict Enum

```python
class EvalVerdict(Enum):
    PASS = "pass"            # 품질 통과 → FINALIZE
    REGENERATE = "regenerate" # 재생성 필요 → REGENERATE
    BLOCK = "block"          # 품질 미달 → FINALIZE (with warning)
```

## 3. Nodes

각 노드는 상태를 읽고 업데이트하는 함수입니다.

### 3.1 Node Summary

| Node | Purpose | Updates | Next |
|------|---------|---------|------|
| ANALYZE | LLM 에이전트 실행 | `response`, `tool_results` | EVALUATE |
| EVALUATE | 응답 품질 평가 | `eval_result`, `check_results` | DECIDE |
| DECIDE | 판정 결정 | `verdict` | FINALIZE or REGENERATE |
| REGENERATE | 재시도 준비 | `feedback`, `attempt++`, reset | ANALYZE |
| FINALIZE | 최종 출력 설정 | `final_response`, `final_status` | END |

### 3.2 ANALYZE Node

Async generator로 스트리밍 이벤트를 전달합니다. 마지막에 `_final=True` 마커가 포함된 dict를 yield합니다.

```python
# src/ops_agent/graph/nodes.py
async def analyze_node(task=None, **kwargs):
    state = get_current_workflow_state()

    # 재시도 시 피드백 포함 프롬프트
    if state.attempt > 0 and state.feedback:
        current_prompt = build_retry_prompt(state.prompt, state.feedback)
    else:
        current_prompt = state.prompt

    # Strands Agent 스트리밍 실행
    agent = _create_agent()
    async for event in agent.stream_async(current_prompt):
        yield event

    # 응답 추출 (마지막 assistant 메시지)
    response = ""
    if hasattr(agent, "messages") and agent.messages:
        for msg in reversed(agent.messages):
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if isinstance(content, dict) and "text" in content:
                        response = content["text"]
                        break
                if response:
                    break

    # 도구 결과 추출
    tool_results = ToolResultExtractor.from_messages(agent.messages)

    # 상태 업데이트
    state.response = response
    state.tool_results = tool_results

    # 최종 결과 (_final 마커)
    yield {"text": response, "tool_results_count": len(tool_results), "_final": True}
```

### 3.3 EVALUATE Node

```python
# src/ops_agent/graph/nodes.py
def evaluate_node(task=None, **kwargs) -> dict[str, Any]:
    state = get_current_workflow_state()

    evaluator = OpsAgentEvaluator()
    eval_result = evaluator.evaluate(
        response=state.response or "",
        tool_results=state.tool_results,
    )

    state.eval_result = eval_result
    state.check_results = eval_result.check_results

    return {"text": f"Score: {eval_result.overall_score:.2f}", ...}
```

### 3.4 DECIDE Node

```python
# src/ops_agent/graph/nodes.py
def decide_node(task=None, **kwargs) -> dict[str, Any]:
    state = get_current_workflow_state()
    score = state.eval_result.overall_score

    if score >= 0.7:
        state.verdict = EvalVerdict.PASS
    elif score < 0.3:
        state.verdict = EvalVerdict.BLOCK
    elif state.attempt >= state.max_attempts - 1:
        state.verdict = EvalVerdict.PASS  # 최대 시도 도달
    else:
        state.verdict = EvalVerdict.REGENERATE

    return {"text": f"{state.verdict.value.upper()} (score={score:.2f})", ...}
```

### 3.5 REGENERATE Node

```python
# src/ops_agent/graph/nodes.py
def regenerate_node(task=None, **kwargs) -> dict[str, Any]:
    state = get_current_workflow_state()

    # 피드백 설정
    if state.eval_result and state.eval_result.feedback:
        state.feedback = state.eval_result.feedback
    else:
        state.feedback = "이전 응답의 품질이 부족합니다. 도구 결과를 더 정확하게 인용해주세요."

    # 시도 횟수 증가 및 상태 초기화
    state.attempt += 1
    state.reset_for_retry()  # response, tool_results, eval_result, verdict 초기화

    return {"text": f"Regenerating (attempt {state.attempt + 1})", ...}
```

### 3.6 FINALIZE Node

```python
# src/ops_agent/graph/nodes.py
def finalize_node(task=None, **kwargs) -> dict[str, Any]:
    state = get_current_workflow_state()

    if state.verdict == EvalVerdict.PASS:
        state.final_response = state.response
        state.final_status = WorkflowStatus.PUBLISHED

    elif state.verdict == EvalVerdict.BLOCK:
        state.final_response = f"⚠️ 응답 품질 검증 주의\n\n{state.response}"
        state.final_status = WorkflowStatus.REJECTED

    else:
        state.final_response = state.response
        state.final_status = WorkflowStatus.PUBLISHED

    return {"text": state.final_response or "", "final_status": state.final_status.value, ...}
```

## 4. Conditions

조건부 라우팅을 위한 함수들입니다.

### 4.1 Condition Functions

조건 함수는 Strands `graph_state`를 인자로 받지만, 실제로는 전역 레지스트리의 `OpsWorkflowState`를 사용합니다.

```python
# src/ops_agent/graph/conditions.py

def should_finalize(graph_state) -> bool:
    """FINALIZE로 진행할지 결정"""
    state = get_current_workflow_state()
    return state.verdict in (EvalVerdict.PASS, EvalVerdict.BLOCK)

def should_regenerate(graph_state) -> bool:
    """REGENERATE로 진행할지 결정"""
    state = get_current_workflow_state()
    return state.verdict == EvalVerdict.REGENERATE
```

### 4.2 Routing Logic (GraphBuilder Edge Definitions)

라우팅은 `_get_next_node()` 같은 함수가 아니라, `GraphBuilder`의 선언적 엣지 정의로 구현됩니다.

```python
# src/ops_agent/graph/runner.py

def build_ops_graph(max_node_executions: int = 15) -> "Graph":
    builder = GraphBuilder()

    # FunctionNode 래퍼 생성 (일반 함수 → MultiAgentBase)
    analyze = FunctionNode(func=analyze_node, name="analyze")
    evaluate = FunctionNode(func=evaluate_node, name="evaluate")
    decide = FunctionNode(func=decide_node, name="decide")
    regenerate = FunctionNode(func=regenerate_node, name="regenerate")
    finalize = FunctionNode(func=finalize_node, name="finalize")

    # 노드 등록
    builder.add_node(analyze, "analyze")
    builder.add_node(evaluate, "evaluate")
    builder.add_node(decide, "decide")
    builder.add_node(regenerate, "regenerate")
    builder.add_node(finalize, "finalize")

    # 진입점
    builder.set_entry_point("analyze")

    # 엣지 정의
    builder.add_edge("analyze", "evaluate")
    builder.add_edge("evaluate", "decide")
    builder.add_edge("decide", "finalize", condition=should_finalize)
    builder.add_edge("decide", "regenerate", condition=should_regenerate)
    builder.add_edge("regenerate", "analyze")  # Loop back

    builder.set_max_node_executions(max_node_executions)
    return builder.build()
```

### 4.3 Decision Matrix

| Score | Attempt | Verdict | Next Node | Final Status |
|-------|---------|---------|-----------|--------------|
| ≥ 0.7 | any | PASS | FINALIZE | PUBLISHED |
| < 0.3 | any | BLOCK | FINALIZE | REJECTED |
| 0.3-0.7 | < max-1 | REGENERATE | REGENERATE → ANALYZE | - |
| 0.3-0.7 | ≥ max-1 | PASS | FINALIZE | PUBLISHED |

## 5. Execution Flow

### 5.1 Runner

Strands `GraphBuilder`가 빌드한 `Graph` 객체를 호출하여 실행합니다. 직접 while 루프를 돌리지 않습니다.

```python
# src/ops_agent/graph/runner.py

def run(self, prompt: str) -> OpsWorkflowState:
    workflow_id = str(uuid.uuid4())

    # 1. 상태 생성 및 전역 레지스트리 등록
    state = create_workflow_state(workflow_id, prompt, self.max_attempts)
    set_current_workflow_id(workflow_id)
    reset_step_counter()

    try:
        # 2. 그래프 실행 (Strands가 노드 순회/조건 평가를 처리)
        result = self._graph(prompt)

        # 3. 최종 상태 반환
        final_state = get_current_workflow_state()
        return final_state if final_state else state

    except Exception as e:
        state.final_status = WorkflowStatus.ERROR
        state.error = str(e)
        return state

    finally:
        set_current_workflow_id(None)
        delete_workflow_state(workflow_id)

async def stream_async(self, prompt: str):
    """AgentCore Runtime 스트리밍용 async generator."""
    # ... (동일 패턴, self._graph.stream_async(prompt) 사용)
```

### 5.2 Example: PASS Flow (score ≥ 0.7)

```
attempt=0
    │
    ▼
ANALYZE ──► response="4건의 에러 발견..."
    │
    ▼
EVALUATE ──► score=1.00
    │
    ▼
DECIDE ──► verdict=PASS
    │
    ▼
FINALIZE ──► final_status=PUBLISHED
    │
    ▼
END
```

### 5.3 Example: REGENERATE Flow (0.3 ≤ score < 0.7)

```
attempt=0
    │
    ▼
ANALYZE ──► response="10건의 에러..." (wrong)
    │
    ▼
EVALUATE ──► score=0.33
    │
    ▼
DECIDE ──► verdict=REGENERATE
    │
    ▼
REGENERATE ──► feedback="실제 이벤트 수는 4건입니다"
              attempt=1
              reset_for_retry()
    │
    └──────────────────┐
                       ▼
attempt=1         ANALYZE ──► response="4건의 에러..." (correct)
                       │
                       ▼
                  EVALUATE ──► score=1.00
                       │
                       ▼
                  DECIDE ──► verdict=PASS
                       │
                       ▼
                  FINALIZE ──► final_status=PUBLISHED
                       │
                       ▼
                      END
```

### 5.4 Example: BLOCK Flow (score < 0.3)

```
attempt=0
    │
    ▼
ANALYZE ──► response="에러가 없습니다" (completely wrong)
    │
    ▼
EVALUATE ──► score=0.10
    │
    ▼
DECIDE ──► verdict=BLOCK
    │
    ▼
FINALIZE ──► final_response="⚠️ 응답 품질 검증 주의\n\n에러가 없습니다"
            final_status=REJECTED
    │
    ▼
END
```

## 6. File Structure

```
src/ops_agent/graph/
├── __init__.py        # Module exports
├── state.py           # OpsWorkflowState, WorkflowStatus, 전역 레지스트리
├── nodes.py           # analyze_node, evaluate_node, decide_node, ...
├── conditions.py      # should_finalize, should_regenerate, ...
├── function_node.py   # FunctionNode (Python 함수 → MultiAgentBase 래퍼)
├── runner.py          # build_ops_graph(), OpsAgentGraph (main runner)
└── util.py            # Colors, StepPrinter, ToolResultExtractor
```

## 7. Usage

### 7.1 Via OpsAgent (Recommended)

```python
from ops_agent.agent import OpsAgent

# Graph 기반 워크플로우 (기본)
agent = OpsAgent(enable_evaluation=True, max_attempts=2)
response = agent.invoke("payment-service에서 500 에러 로그 보여줘")
print(response)
```

### 7.2 Direct Graph Usage

```python
from ops_agent.graph.runner import OpsAgentGraph

graph = OpsAgentGraph(max_attempts=2, verbose=True)
result = graph.run("payment-service에서 500 에러 로그 보여줘")

print(f"Status: {result.final_status.value}")
print(f"Verdict: {result.verdict.value}")
print(f"Score: {result.eval_result.overall_score}")
print(f"Response: {result.final_response}")
```

## 8. References

- Self-Correcting Translation Agent: https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent
- Evaluation Design: [docs/evaluation-design.md](./evaluation-design.md)
- Research Guide: [docs/research-guide-results.md](./research-guide-results.md)
