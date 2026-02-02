# OpsAgent - Self-Correcting Operations AI Agent

운영 자동화를 위한 AI 에이전트입니다. **3단계 평가 시스템**으로 응답 품질을 검증하고, 피드백 기반으로 자체 개선하며, 운영자의 의사결정을 지원합니다.

## 해결하고자 하는 문제

운영 환경에서 AI 에이전트를 사용할 때 다음과 같은 문제가 발생합니다:

| 문제 | 설명 |
|------|------|
| **품질 일관성 부재** | LLM 응답 품질이 일정하지 않아 신뢰성 저하 |
| **환각(Hallucination)** | 도구 결과와 무관한 허위 정보 생성 |
| **검증 부재** | 응답이 도구 결과를 정확히 인용하는지 확인 불가 |
| **감사 추적 어려움** | 비결정적 LLM 출력으로 감사 대응 곤란 |
| **자동 개선 미흡** | 피드백 기반 자체 개선 메커니즘 부재 |

## 솔루션 아키텍처

**5단계 파이프라인**으로 품질을 보장합니다:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     OpsAgent Evaluation Graph                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   START                                                                  │
│     │                                                                    │
│     ▼                                                                    │
│   ┌──────────┐                                                           │
│   │ ANALYZE  │  LLM 에이전트 실행, CloudWatch/Datadog 도구 호출           │
│   └────┬─────┘                                                           │
│        │                                                                 │
│        ▼                                                                 │
│   ┌──────────┐                                                           │
│   │ EVALUATE │  응답 품질 평가 (도구 결과 인용, 정확성, 완전성)             │
│   └────┬─────┘                                                           │
│        │                                                                 │
│        ▼                                                                 │
│   ┌──────────┐                                                           │
│   │  DECIDE  │  SOP 기반 판정 (PASS / REGENERATE / BLOCK)                │
│   └────┬─────┘                                                           │
│        │                                                                 │
│        ├── PASS/BLOCK ──────▶ ┌──────────┐                               │
│        │                      │ FINALIZE │ ──▶ 최종 응답 출력              │
│        │                      └──────────┘                               │
│        │                                                                 │
│        └── REGENERATE ──────▶ ┌────────────┐                             │
│                               │ REGENERATE │ ──▶ 피드백과 함께 ANALYZE 재실행│
│                               └────────────┘                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 핵심 기술

| 기능 | 설명 |
|------|------|
| **Graph 기반 워크플로우** | Strands GraphBuilder로 선언적 워크플로우 정의 |
| **자체 교정 루프** | 평가 피드백을 반영하여 응답 자동 재생성 |
| **도구 결과 검증** | 응답이 실제 도구 결과를 정확히 인용하는지 검증 |
| **설명 가능한 평가** | 점수와 함께 평가 근거 제공 |
| **실시간 스트리밍** | 토큰 단위 실시간 응답 스트리밍 |
| **AgentCore 배포** | AWS Bedrock AgentCore Runtime 배포 지원 |

## 평가 시스템

### 점수 기반 판정

| 점수 | 판정 | 동작 |
|------|------|------|
| **≥ 0.7** | PASS | 즉시 게시 |
| **0.3 ~ 0.7** | REGENERATE | 피드백과 함께 재생성 (최대 2회) |
| **< 0.3** | BLOCK | 품질 경고와 함께 게시 |

### 평가 항목

- **도구 결과 인용**: 응답이 도구 결과의 데이터를 정확히 인용하는가
- **정확성**: 숫자, 날짜, 서비스명 등이 정확한가
- **완전성**: 사용자 질문에 충분히 답변했는가
- **일관성**: 응답 내 모순이 없는가

## 기술 스택

| 구성요소 | 기술 |
|----------|------|
| Language | Python 3.11+ |
| LLM | AWS Bedrock Claude Sonnet 4 |
| Agent Framework | Strands Agents SDK |
| Deployment | AWS Bedrock AgentCore Runtime |
| Observability | Langfuse, CloudWatch, X-Ray |

## 프로젝트 구조

```
AI-Ops-Agent-AgentCore/
├── agentcore/                    # AgentCore 배포
│   ├── runtime/
│   │   └── entrypoint.py         # Runtime 진입점
│   └── scripts/
│       ├── deploy.py             # 배포 스크립트
│       ├── invoke.py             # CLI 클라이언트
│       └── util.py               # 유틸리티
│
├── src/ops_agent/                # 메인 소스코드
│   ├── agent/
│   │   └── ops_agent.py          # OpsAgent 클래스
│   ├── graph/                    # Graph 워크플로우
│   │   ├── nodes.py              # 노드 구현
│   │   ├── runner.py             # Graph 실행기
│   │   ├── state.py              # 워크플로우 상태
│   │   ├── conditions.py         # 조건 함수
│   │   ├── function_node.py      # FunctionNode 래퍼
│   │   └── util.py               # 공통 유틸리티
│   ├── evaluation/               # 평가 시스템
│   │   ├── evaluator.py          # 평가기
│   │   └── models.py             # 평가 모델
│   ├── tools/                    # 도구
│   │   └── cloudwatch/           # CloudWatch 도구
│   ├── telemetry/                # 관측성 (Langfuse/OTEL)
│   │   ├── __init__.py
│   │   └── setup.py              # 관측성 설정
│   ├── prompts/                  # 시스템 프롬프트
│   └── config/                   # 설정
│
├── docs/                         # 문서
│   └── streaming-implementation.md
│
└── tests/                        # 테스트
```

## 빠른 시작

### 요구사항

- Python 3.11+
- AWS 자격 증명 (Bedrock, CloudWatch 권한)
- uv (패키지 관리자)

### 설치

```bash
# 저장소 클론
git clone <repository-url>
cd AI-Ops-Agent-AgentCore

# 환경 설정 (uv 설치, 의존성)
./setup/create_env.sh

# 환경 변수 파일 생성 및 설정
cp .env.example .env
vi .env  # AWS 자격 증명 등 설정
```

### AgentCore 배포

```bash
cd agentcore

# 인프라 설정 (IAM Role, ECR 등)
./deploy_infra.sh

# 에이전트 배포
uv run python scripts/deploy.py --auto-update

# 테스트
uv run python scripts/invoke.py --test simple

# 대화형 모드
uv run python scripts/invoke.py --interactive
```

## 사용 예시

### 한국어

```
> payment-service에서 최근 1시간 동안 ERROR 로그 보여줘
> Lambda 함수 timeout 에러 분석해줘
> order-service의 최근 30분간 500 에러 조회해줘
```

### English

```
> Show me ERROR logs from payment-service in the last hour
> Analyze Lambda function timeout errors
> Query 500 errors from order-service in the last 30 minutes
```

## 설정

### 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AWS_REGION` | AWS 리전 | `us-east-1` |
| `BEDROCK_MODEL_ID` | Claude 모델 ID | `us.anthropic.claude-sonnet-4-20250514` |
| `BEDROCK_TEMPERATURE` | 응답 다양성 | `0.3` |
| `BEDROCK_MAX_TOKENS` | 최대 토큰 수 | `4096` |

## CLI 사용법

```bash
# 단일 프롬프트
uv run python scripts/invoke.py --prompt "payment-service 에러 보여줘"

# 테스트 프롬프트 (simple, error, timeout, analysis)
uv run python scripts/invoke.py --test simple

# 토큰별 타이밍 출력
uv run python scripts/invoke.py --test simple --verbose

# 원시 이벤트 출력 (디버깅용)
uv run python scripts/invoke.py --test simple --raw

# 대화형 모드
uv run python scripts/invoke.py --interactive
```

## 문서

| 문서 | 설명 |
|------|------|
| [환경 설정 가이드](docs/environment-configuration.md) | 환경 변수 및 .env 설정 |
| [Observability & Langfuse](docs/observability-langfuse.md) | Langfuse 통합 및 관측성 설정 |
| [스트리밍 구현](docs/streaming-implementation.md) | 실시간 스트리밍 아키텍처 |
| [Graph 워크플로우](docs/graph-workflow.md) | 평가 그래프 설계 및 구현 |
| [평가 시스템 설계](docs/evaluation-design.md) | 응답 품질 평가 시스템 |
| [연구 가이드 결과](docs/research-guide-results.md) | Strands SDK 연구 및 패턴 |

## 참고 자료

- [Strands Agents SDK](https://strandsagents.com/)
- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Self-Correcting Translation Agent](https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent)

## 라이선스

MIT License
