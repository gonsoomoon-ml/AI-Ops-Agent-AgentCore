# KB Evaluation (KBChecker)

> Knowledge Base 응답 품질 평가 시스템
> 작성일: 2026-02-10

---

## 목차

1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [KBChecker 상세](#3-kbchecker-상세)
4. [평가 흐름](#4-평가-흐름)
5. [파일 구조](#5-파일-구조)
6. [테스트](#6-테스트)

---

## 1. 개요

KBChecker는 KB 검색 결과의 핵심 내용이 에이전트 응답에 반영되었는지를 검사하는 평가기입니다.

기존 CloudWatchChecker와 동일한 `BaseChecker` 패턴을 따르며, `OpsAgentEvaluator`에 등록되어 Graph 워크플로우의 EVALUATE 단계에서 자동 실행됩니다.

| 항목 | CloudWatchChecker | KBChecker |
|------|-------------------|-----------|
| 검사 대상 | CloudWatch 로그 이벤트 | KB 검색 결과 문서 |
| 검사 항목 수 | 3 (이벤트수, 에러인용, 서비스명) | 1 (핵심 키워드 반영) |
| 핵심 검사 | 숫자/에러 정확 인용 | KB 문서 핵심 구문이 응답에 포함 |
| 통과 임계값 | 0.7 | 0.7 |

## 2. 아키텍처

### Graph 워크플로우

```
User Query
    │
    ▼
┌──────────┐
│ ANALYZE  │  Strands Agent 실행 → kb_retrieve 도구 호출 → 응답 생성
└────┬─────┘
     │
     ▼
┌──────────┐
│ EVALUATE │  CloudWatchChecker + KBChecker 실행
└────┬─────┘
     │
     ▼
┌──────────┐
│  DECIDE  │  score ≥ 0.7 → PASS / 0.3~0.7 → REGENERATE / < 0.3 → BLOCK
└────┬─────┘
     │
     ├── PASS/BLOCK ──▶ FINALIZE → END
     │
     └── REGENERATE ──▶ REGENERATE → ANALYZE (loop, max 2x)
```

### Evaluator 내부 동작

```
OpsAgentEvaluator.evaluate(response, tool_results)
    │
    ├── CloudWatchChecker.check()
    │     └── CW 결과 없으면 → score=1.0 (스킵)
    │
    ├── KBChecker.check()
    │     └── KB 결과에서 핵심 구문 추출 → 응답에 포함 여부 확인
    │
    ▼
    overall_score = average(checker_scores)
    verdict = PASS / REGENERATE / BLOCK
```

**핵심**: KB 질문 시 CloudWatch 결과가 없으므로 CloudWatchChecker는 `score=1.0`으로 스킵. KBChecker만 실질적 평가를 수행합니다.

## 3. KBChecker 상세

### 위치

`src/ops_agent/evaluation/checkers/knowledge_base.py`

### 검사 로직

1. `tool_results`에서 `ToolType.KNOWLEDGE_BASE` 결과만 필터링
2. KB 결과 없으면 `score=1.0` (스킵)
3. 상위 결과(`results[0]`)의 `content`에서 핵심 구문 추출
4. 각 구문이 응답에 포함되었는지 확인
5. `score = found_phrases / total_phrases`

### 핵심 구문 추출 (`_extract_key_phrases`)

KB 문서는 LLM enrichment로 다음 구조를 가집니다:

```markdown
## 질문
TSS Activation이 뭐야?

## 답변
TSS Activation은 ...

## 핵심 키워드
TSS, Activation, TSS 2.0, 활성화, ...
```

추출 우선순위:
1. **`## 핵심 키워드` 섹션** → 쉼표로 분리, 2글자 이상만 (최대 8개)
2. **`## 답변` 섹션** (키워드 부족 시 보충) → 3글자+ 단어 추출 (최대 8개까지)

### 점수 판정

| 점수 | 판정 |
|------|------|
| ≥ 0.7 | PASS — 응답이 KB 내용을 충분히 반영 |
| 0.3 ~ 0.7 | REGENERATE — 피드백과 함께 재생성 |
| < 0.3 | BLOCK — 경고와 함께 반환 |

### ToolType 감지

`graph/util.py`의 `infer_tool_type()`이 도구 결과 JSON 구조로 유형 추론:

```python
# kb_retrieve 반환 JSON에 "kb_id" 키 포함
if any(key in output for key in ["kb_id", "documents", "sources", "chunks"]):
    return ToolType.KNOWLEDGE_BASE
```

## 4. 평가 흐름

### KB 결과가 있는 경우

```
kb_retrieve → {"kb_id": "G5GG6ZV8GX", "results": [{content: "## 핵심 키워드\nTSS, Activation, ..."}]}
                                                          │
                                                          ▼
KBChecker._extract_key_phrases(content)  →  ["TSS", "Activation", "TSS 2.0", ...]
                                                          │
                                                          ▼
각 phrase가 response에 포함? → found: 7/8 → score: 0.875 → PASS
```

### KB 결과가 없는 경우 (CloudWatch 질문)

```
CloudWatchChecker → score: 0.85 (CW 데이터 정확 인용)
KBChecker         → score: 1.0  (KB 결과 없음, 스킵)
overall_score     → (0.85 + 1.0) / 2 = 0.925 → PASS
```

### REGENERATE 시나리오

```
1차 ANALYZE → response에 KB 키워드 3/8만 포함
EVALUATE → KBChecker score: 0.375 → REGENERATE
피드백: "미반영: TSS 2.0, 활성화, ..."
REGENERATE → 피드백 포함 프롬프트 생성
2차 ANALYZE → 피드백 반영하여 재생성
EVALUATE → KBChecker score: 0.875 → PASS
```

## 5. 파일 구조

### 변경/추가된 파일

| 파일 | 변경 내용 |
|------|-----------|
| `evaluation/checkers/knowledge_base.py` | **NEW** — KBChecker 구현 |
| `evaluation/checkers/__init__.py` | KBChecker export 추가 |
| `evaluation/evaluator.py` | KBChecker() 등록 |
| `graph/util.py` | `infer_tool_type()`에 `"kb_id"` 감지 추가 |
| `tests/test_manual.py` | test_9 추가 |

### BaseChecker 패턴

모든 검사기는 동일한 패턴을 따릅니다:

```python
class KBChecker(BaseChecker):
    PASS_THRESHOLD = 0.7

    @property
    def name(self) -> str:
        return "kb_accuracy"

    def check(self, response: str, tool_results: list[ToolResult]) -> CheckResult:
        # 1. 해당 ToolType 필터링
        # 2. 결과 없으면 score=1.0 스킵
        # 3. 검사 로직 실행
        # 4. CheckResult 반환
```

### Evaluator 등록

```python
# evaluation/evaluator.py
class OpsAgentEvaluator:
    def __init__(self):
        self.checkers: list[BaseChecker] = [
            CloudWatchChecker(),
            KBChecker(),
            # DatadogChecker(),       # Phase 2
        ]
```

## 6. 테스트

### test_9: KB + Graph 평가 워크플로우

```bash
uv run python tests/test_manual.py --test 9
```

실행 내용:
- `OpsAgent(enable_evaluation=True)` — Graph 모드
- 질문: `"TSS Activation이 뭐야?"`
- ANALYZE → EVALUATE (KBChecker) → DECIDE → FINALIZE

예상 출력:

```
[1] ANALYZE - LLM 에이전트 실행 (시도 1/2)
    응답 길이: 1200자
    도구 호출: 1건

[2] EVALUATE - 응답 품질 평가
    점수: 1.00
    검사 항목: 2개

[3] DECIDE - 판정 결정
    판정: PASS
    점수: 1.00
    사유: score_pass

[4] FINALIZE - 최종 출력 결정
    상태: PUBLISHED
    응답 길이: 1200자
```

### test_8 vs test_9

| | test_8 | test_9 |
|--|--------|--------|
| 모드 | `enable_evaluation=False` | `enable_evaluation=True` |
| 실행 | Agent 직접 호출 | Graph 워크플로우 |
| 평가 | 없음 | KBChecker + CloudWatchChecker |
| 용도 | KB 연결 확인 | 평가 파이프라인 검증 |

```bash
# test_8: KB 연결만 확인
uv run python tests/test_manual.py --test 8

# test_9: 전체 평가 파이프라인
uv run python tests/test_manual.py --test 9
```
