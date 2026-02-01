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

```python
def analyze_node(state: OpsWorkflowState) -> dict[str, Any]:
    # 재시도 시 피드백 포함
    if state.attempt > 0 and state.feedback:
        prompt = f"{state.prompt}\n\n피드백: {state.feedback}"
    else:
        prompt = state.prompt

    # Strands Agent 실행
    agent = _create_agent()
    result = agent(prompt)

    # 상태 업데이트
    state.response = result.message["content"][0]["text"]
    state.tool_results = _capture_tool_results(result)

    return {"response": state.response, "tool_results_count": len(state.tool_results)}
```

### 3.3 EVALUATE Node

```python
def evaluate_node(state: OpsWorkflowState) -> dict[str, Any]:
    evaluator = OpsAgentEvaluator()
    eval_result = evaluator.evaluate(
        response=state.response,
        tool_results=state.tool_results,
    )

    state.eval_result = eval_result
    state.check_results = eval_result.check_results

    return {"overall_score": eval_result.overall_score}
```

### 3.4 DECIDE Node

```python
def decide_node(state: OpsWorkflowState) -> dict[str, Any]:
    score = state.eval_result.overall_score

    if score >= 0.7:
        state.verdict = EvalVerdict.PASS
    elif score < 0.3:
        state.verdict = EvalVerdict.BLOCK
    elif state.attempt >= state.max_attempts - 1:
        state.verdict = EvalVerdict.PASS  # 최대 시도 도달
    else:
        state.verdict = EvalVerdict.REGENERATE

    return {"verdict": state.verdict.value, "score": score}
```

### 3.5 REGENERATE Node

```python
def regenerate_node(state: OpsWorkflowState) -> dict[str, Any]:
    # 피드백 설정
    state.feedback = state.eval_result.feedback

    # 시도 횟수 증가
    state.attempt += 1

    # 재시도를 위한 상태 초기화
    state.reset_for_retry()  # response, tool_results, eval_result, verdict 초기화

    return {"attempt": state.attempt}
```

### 3.6 FINALIZE Node

```python
def finalize_node(state: OpsWorkflowState) -> dict[str, Any]:
    if state.verdict == EvalVerdict.PASS:
        state.final_response = state.response
        state.final_status = WorkflowStatus.PUBLISHED

    elif state.verdict == EvalVerdict.BLOCK:
        state.final_response = f"⚠️ 품질 검증 주의\n\n{state.response}"
        state.final_status = WorkflowStatus.REJECTED

    return {"final_status": state.final_status.value}
```

## 4. Conditions

조건부 라우팅을 위한 함수들입니다.

### 4.1 Condition Functions

```python
# graph/conditions.py

def should_finalize(state: OpsWorkflowState) -> bool:
    """FINALIZE로 진행할지 결정"""
    return state.verdict in (EvalVerdict.PASS, EvalVerdict.BLOCK)

def should_regenerate(state: OpsWorkflowState) -> bool:
    """REGENERATE로 진행할지 결정"""
    return state.verdict == EvalVerdict.REGENERATE
```

### 4.2 Routing Logic

```python
# graph/runner.py - _get_next_node()

def _get_next_node(current_node: NodeName, state: OpsWorkflowState) -> NodeName:
    if current_node == NodeName.ANALYZE:
        return NodeName.EVALUATE

    elif current_node == NodeName.EVALUATE:
        return NodeName.DECIDE

    elif current_node == NodeName.DECIDE:
        if should_finalize(state):      # PASS or BLOCK
            return NodeName.FINALIZE
        elif should_regenerate(state):  # REGENERATE
            return NodeName.REGENERATE
        else:
            return NodeName.FINALIZE    # Default

    elif current_node == NodeName.REGENERATE:
        return NodeName.ANALYZE         # Loop back

    elif current_node == NodeName.FINALIZE:
        return NodeName.END
```

### 4.3 Decision Matrix

| Score | Attempt | Verdict | Next Node | Final Status |
|-------|---------|---------|-----------|--------------|
| ≥ 0.7 | any | PASS | FINALIZE | PUBLISHED |
| < 0.3 | any | BLOCK | FINALIZE | REJECTED |
| 0.3-0.7 | < max-1 | REGENERATE | REGENERATE → ANALYZE | - |
| 0.3-0.7 | ≥ max-1 | PASS | FINALIZE | PUBLISHED |

## 5. Execution Flow

### 5.1 Runner Loop

```python
# graph/runner.py

def run(self, prompt: str) -> OpsWorkflowState:
    # 1. 상태 생성
    state = create_workflow_state(workflow_id, prompt, max_attempts)

    # 2. 그래프 실행 루프
    current_node = NodeName.ANALYZE
    node_count = 0

    while current_node != NodeName.END:
        # 무한 루프 방지
        node_count += 1
        if node_count > self.max_node_executions:
            state.error = "Maximum node executions exceeded"
            break

        # 노드 실행
        result = self._execute_node(current_node, state)

        # 다음 노드로 이동
        current_node = result.next_node

    # 3. 상태 정리 및 반환
    delete_workflow_state(workflow_id)
    return state
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
FINALIZE ──► final_response="⚠️ 품질 검증 주의\n\n에러가 없습니다"
            final_status=REJECTED
    │
    ▼
END
```

## 6. File Structure

```
src/ops_agent/graph/
├── __init__.py      # Module exports
├── state.py         # OpsWorkflowState, WorkflowStatus
├── nodes.py         # analyze_node, evaluate_node, decide_node, ...
├── conditions.py    # should_finalize, should_regenerate
└── runner.py        # OpsAgentGraph (main runner)
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
