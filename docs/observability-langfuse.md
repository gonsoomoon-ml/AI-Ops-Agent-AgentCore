# Observability & Langfuse 통합 가이드

OpsAgent의 관측성(Observability) 설정 가이드입니다. Strands (로컬 개발)와 AgentCore (프로덕션 배포) 환경 각각에 대해 Langfuse 또는 AWS 네이티브 관측성을 설정할 수 있습니다.

## 목차

- [개요](#개요)
- [지원하는 5가지 모드](#지원하는-5가지-모드)
- [Langfuse 소개](#langfuse-소개)
- [설정 방법](#설정-방법)
  - [Strands (로컬 개발)](#strands-로컬-개발)
  - [AgentCore (프로덕션 배포)](#agentcore-프로덕션-배포)
- [환경 변수 참조](#환경-변수-참조)
- [사용 예시](#사용-예시)
- [트러블슈팅](#트러블슈팅)

## 개요

OpsAgent는 두 가지 환경에서 실행됩니다:

| 환경 | 설명 | 관측성 옵션 |
|------|------|-------------|
| **Strands (로컬)** | 로컬 개발 및 테스트 | Langfuse Public, Langfuse Self-hosted |
| **AgentCore (프로덕션)** | AWS Bedrock AgentCore 런타임 배포 | Langfuse Public, Langfuse Self-hosted, AWS Native (ADOT) |

```
┌─────────────────────────────────────────────────────────────────┐
│                    Observability 아키텍처                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Strands Agent ──┬── Langfuse Public Cloud                     │
│   (로컬 개발)      └── Langfuse Self-hosted                      │
│                                                                  │
│   AgentCore ──────┬── Langfuse Public Cloud                     │
│   (프로덕션)       ├── Langfuse Self-hosted                      │
│                    └── AWS ADOT (CloudWatch/X-Ray)              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 지원하는 5가지 모드

| # | 환경 | 모드 | 백엔드 | 사용 사례 |
|---|------|------|--------|----------|
| 1 | Strands | `langfuse-public` | Langfuse Cloud | 로컬 개발 + 클라우드 관측성 |
| 2 | Strands | `langfuse-selfhosted` | Self-hosted Langfuse | 로컬 개발 + VPC 내 관측성 |
| 3 | AgentCore | `langfuse-public` | Langfuse Cloud | 프로덕션 + 클라우드 관측성 |
| 4 | AgentCore | `langfuse-selfhosted` | Self-hosted Langfuse | 프로덕션 + VPC 내 관측성 |
| 5 | AgentCore | `native` | AWS ADOT | 프로덕션 + AWS 네이티브 관측성 |

## Langfuse 소개

[Langfuse](https://langfuse.com/)는 오픈소스 LLM 관측성 플랫폼입니다.

### 주요 기능

| 기능 | 설명 |
|------|------|
| **트레이스 시각화** | 에이전트 실행 흐름을 계층적으로 시각화 |
| **비용 추적** | 모델별 토큰 사용량 및 비용 분석 |
| **LLM Playground** | 프롬프트 재실행 및 테스트 |
| **평가 (Evaluations)** | LLM-as-a-judge 자동 평가 |
| **프롬프트 관리** | 버전 관리 및 A/B 테스트 |
| **세션 분석** | 멀티턴 대화 그룹화 및 분석 |

### 호스팅 옵션

| 옵션 | 장점 | 단점 |
|------|------|------|
| **Langfuse Cloud** | 즉시 사용 가능, 무료 티어 제공 | 데이터가 외부 클라우드에 저장 |
| **Self-hosted** | 완전한 데이터 제어, VPC 내 운영 | 인프라 관리 필요 |

## 설정 방법

### Strands (로컬 개발)

#### 모드 1: Langfuse Public Cloud

1. [Langfuse Cloud](https://us.cloud.langfuse.com) 계정 생성
2. 프로젝트 생성 후 API 키 발급
3. `.env` 파일 설정:

```bash
# Strands 관측성 모드 설정
STRANDS_OBSERVABILITY_MODE=langfuse-public

# Langfuse Public Cloud API 키
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_PUBLIC_ENDPOINT=https://us.cloud.langfuse.com
```

4. 에이전트 실행:

```bash
uv run ops-agent
```

#### 모드 2: Langfuse Self-hosted

1. Self-hosted Langfuse 배포 (ECS Fargate 권장)
2. `.env` 파일 설정:

```bash
# Strands 관측성 모드 설정
STRANDS_OBSERVABILITY_MODE=langfuse-selfhosted

# Langfuse Self-hosted API 키
LANGFUSE_SELFHOSTED_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SELFHOSTED_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_SELFHOSTED_ENDPOINT=http://your-alb.region.elb.amazonaws.com
```

### AgentCore (프로덕션 배포)

AgentCore 런타임 배포 시 `get_agentcore_observability_env_vars()` 함수를 사용하여 환경 변수를 전달합니다.

#### 모드 3: Langfuse Public Cloud

```bash
# .env 설정
AGENTCORE_OBSERVABILITY_MODE=langfuse-public
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
```

```python
# 배포 코드
from ops_agent.telemetry import get_agentcore_observability_env_vars
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
runtime.configure(
    entrypoint="entrypoint.py",
    disable_otel=True,  # AWS ADOT 비활성화
    # ... 기타 설정
)

# Langfuse 환경 변수 전달
env_vars = get_agentcore_observability_env_vars()
runtime.launch(env_vars=env_vars)
```

#### 모드 4: Langfuse Self-hosted

```bash
# .env 설정
AGENTCORE_OBSERVABILITY_MODE=langfuse-selfhosted
LANGFUSE_SELFHOSTED_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SELFHOSTED_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_SELFHOSTED_ENDPOINT=http://your-alb.region.elb.amazonaws.com
```

#### 모드 5: AWS Native (ADOT)

```bash
# .env 설정
AGENTCORE_OBSERVABILITY_MODE=native
```

```python
# 배포 코드 - ADOT는 기본 활성화
runtime.configure(
    entrypoint="entrypoint.py",
    # disable_otel=False (기본값)
)
runtime.launch()  # env_vars 불필요
```

## 환경 변수 참조

### 모드 설정

| 변수 | 설명 | 값 |
|------|------|-----|
| `STRANDS_OBSERVABILITY_MODE` | Strands 로컬 관측성 모드 | `disabled`, `langfuse-public`, `langfuse-selfhosted` |
| `AGENTCORE_OBSERVABILITY_MODE` | AgentCore 관측성 모드 | `disabled`, `langfuse-public`, `langfuse-selfhosted`, `native` |
| `OTEL_SERVICE_NAME` | 서비스 이름 (트레이스에 표시) | 기본값: `ops-ai-agent` |

### Langfuse Public Cloud

| 변수 | 설명 | 예시 |
|------|------|------|
| `LANGFUSE_PUBLIC_KEY` | Public API 키 | `pk-lf-xxxxxxxx` |
| `LANGFUSE_SECRET_KEY` | Secret API 키 | `sk-lf-xxxxxxxx` |
| `LANGFUSE_PUBLIC_ENDPOINT` | Langfuse Cloud URL | `https://us.cloud.langfuse.com` |

### Langfuse Self-hosted

| 변수 | 설명 | 예시 |
|------|------|------|
| `LANGFUSE_SELFHOSTED_PUBLIC_KEY` | Public API 키 | `pk-lf-xxxxxxxx` |
| `LANGFUSE_SELFHOSTED_SECRET_KEY` | Secret API 키 | `sk-lf-xxxxxxxx` |
| `LANGFUSE_SELFHOSTED_ENDPOINT` | Self-hosted URL | `http://your-alb.region.elb.amazonaws.com` |

## 사용 예시

### OpsAgent 초기화 (세션/사용자 추적)

```python
from ops_agent.agent import OpsAgent

# 세션 및 사용자 ID를 지정하여 Langfuse에서 그룹화
agent = OpsAgent(
    session_id="session-123",      # 세션별 트레이스 그룹화
    user_id="user@example.com",    # 사용자별 분석
)

response = agent.invoke("payment-service 에러 로그 보여줘")
```

### Telemetry 모듈 직접 사용

```python
from ops_agent.telemetry import (
    setup_strands_observability,
    get_agentcore_observability_env_vars,
    get_trace_attributes,
)

# Strands 로컬 관측성 설정
if setup_strands_observability():
    print("Langfuse 관측성 활성화됨")

# AgentCore 환경 변수 조회
env_vars = get_agentcore_observability_env_vars()
print(env_vars)
# {'DISABLE_ADOT_OBSERVABILITY': 'true',
#  'OTEL_EXPORTER_OTLP_ENDPOINT': 'https://...',
#  'OTEL_EXPORTER_OTLP_HEADERS': 'Authorization=Basic ...'}

# Agent 트레이스 속성 생성
attrs = get_trace_attributes(session_id="session-123", user_id="user@example.com")
print(attrs)
# {'langfuse.tags': ['langfuse-public', 'ops-ai-agent'],
#  'session.id': 'session-123',
#  'user.id': 'user@example.com'}
```

## 트러블슈팅

### 트레이스가 Langfuse에 표시되지 않음

1. **API 키 확인**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`가 올바르게 설정되었는지 확인
2. **엔드포인트 확인**: `LANGFUSE_PUBLIC_ENDPOINT` URL이 올바른지 확인
3. **네트워크 확인**: Langfuse 서버에 접근 가능한지 확인

```bash
# 연결 테스트
curl -v https://us.cloud.langfuse.com/api/public/health
```

### strands-agents[otel] 패키지 오류

```bash
# OTEL 패키지 설치
pip install strands-agents[otel]
# 또는
uv add strands-agents[otel]
```

### AgentCore에서 ADOT와 Langfuse 충돌

AgentCore 런타임에서 Langfuse를 사용할 때는 반드시 AWS ADOT를 비활성화해야 합니다:

```python
runtime.configure(
    disable_otel=True,  # AWS ADOT 비활성화
)

env_vars = get_agentcore_observability_env_vars()  # Langfuse 환경 변수
runtime.launch(env_vars=env_vars)
```

## 참고 자료

- [Langfuse Documentation](https://langfuse.com/docs)
- [Langfuse GitHub](https://github.com/langfuse/langfuse)
- [Strands Agents Telemetry](https://strandsagents.com/latest/user-guide/observability/)
- [AWS Bedrock AgentCore Observability](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-observability.html)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
