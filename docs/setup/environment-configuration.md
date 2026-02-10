# 환경 설정 가이드

OpsAgent 실행을 위한 환경 변수 설정 가이드입니다.

## 설정 파일 생성

```bash
cp .env.example .env
vi .env
```

## 환경 변수 상세

### AWS 설정

| 변수 | 설명 | 기본값 | 필수 |
|------|------|--------|------|
| `AWS_REGION` | AWS 리전 | `us-east-1` | O |
| `AWS_PROFILE` | AWS CLI 프로필 | `default` | X |

```bash
AWS_REGION=us-east-1
# AWS_PROFILE=default
```

### Bedrock 설정

| 변수 | 설명 | 기본값 | 필수 |
|------|------|--------|------|
| `BEDROCK_MODEL_ID` | Claude 모델 ID | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | O |
| `BEDROCK_TEMPERATURE` | 응답 다양성 (0.0~1.0) | `0.0` | X |
| `BEDROCK_MAX_TOKENS` | 최대 토큰 수 | `4096` | X |
| `BEDROCK_KNOWLEDGE_BASE_ID` | Knowledge Base ID | - | X (KB 사용 시) |

```bash
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_TEMPERATURE=0.0
BEDROCK_MAX_TOKENS=4096
```

**사용 가능한 모델:**

| 모델 ID | 설명 |
|---------|------|
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | 기본값, 빠른 응답 |
| `global.anthropic.claude-opus-4-5-20251101-v1:0` | 고성능, 복잡한 분석 |

**프롬프트 캐싱:**
- 시스템 프롬프트와 도구 정의에 `cachePoint`를 설정하여 최대 90% 비용 절감
- 항상 활성화 (별도 설정 불필요)

### Datadog 설정 (Phase 2)

| 변수 | 설명 | 기본값 | 필수 |
|------|------|--------|------|
| `DATADOG_API_KEY` | Datadog API 키 | - | X |
| `DATADOG_APP_KEY` | Datadog App 키 | - | X |
| `DATADOG_SITE` | Datadog 사이트 | `datadoghq.com` | X |

```bash
# DATADOG_API_KEY=your-api-key-here
# DATADOG_APP_KEY=your-app-key-here
DATADOG_SITE=datadoghq.com
```

### Agent 설정

| 변수 | 설명 | 기본값 | 필수 |
|------|------|--------|------|
| `AGENT_LANGUAGE` | 응답 언어 | `ko` | X |
| `AGENT_LOG_LEVEL` | 로그 레벨 | `INFO` | X |

```bash
AGENT_LANGUAGE=ko        # ko | en
AGENT_LOG_LEVEL=INFO     # DEBUG | INFO | WARNING | ERROR
```

### 도구 모드 설정

`.env`에서 `mock` ↔ `mcp`를 전환하여 테스트/운영 환경을 분리합니다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `CLOUDWATCH_MODE` | CloudWatch 도구 모드 | `mock` |
| `DATADOG_MODE` | Datadog 도구 모드 (Phase 2) | `mock` |
| `KB_MODE` | Knowledge Base 도구 모드 | `mock` |

```bash
# 개발/테스트 환경 — 실제 API 호출 없음
CLOUDWATCH_MODE=mock          # 모의 CloudWatch 데이터
DATADOG_MODE=mock             # Phase 2
KB_MODE=mock                  # 로컬 YAML 기반 KB 검색

# 운영 환경 — 실제 API 호출
CLOUDWATCH_MODE=mcp           # MCP 서버 → CloudWatch API
KB_MODE=mcp                   # Bedrock KB HYBRID 검색
```

> **참고**: `KB_MODE=mcp` 사용 시 `BEDROCK_KNOWLEDGE_BASE_ID` 설정이 필요합니다.

### AgentCore Memory 설정

대화 컨텍스트를 유지하기 위한 메모리 설정입니다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AGENTCORE_MEMORY_ENABLED` | 메모리 활성화 | `false` |
| `AGENTCORE_MEMORY_ID` | 메모리 ID | - |
| `AGENTCORE_SESSION_TTL` | 세션 TTL (초) | `3600` |

```bash
AGENTCORE_MEMORY_ENABLED=false
# AGENTCORE_MEMORY_ID=your-memory-id-here
AGENTCORE_SESSION_TTL=3600
```

### Observability 설정

로컬 개발(Strands)과 프로덕션(AgentCore)에서 각각 별도의 관측성 모드를 설정합니다. 자세한 설정은 [Observability & Langfuse](observability-langfuse.md)를 참고하세요.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `STRANDS_OBSERVABILITY_MODE` | 로컬 관측성 모드 | `disabled` |
| `AGENTCORE_OBSERVABILITY_MODE` | AgentCore 관측성 모드 | `disabled` |
| `OTEL_SERVICE_NAME` | 서비스 이름 | `ops-ai-agent` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse Public Cloud API 키 | - |
| `LANGFUSE_SECRET_KEY` | Langfuse Public Cloud Secret 키 | - |
| `LANGFUSE_PUBLIC_ENDPOINT` | Langfuse Public Cloud 엔드포인트 | `https://us.cloud.langfuse.com` |

```bash
# 로컬 개발 — Langfuse Cloud로 트레이싱
STRANDS_OBSERVABILITY_MODE=langfuse-public    # disabled | langfuse-public | langfuse-selfhosted

# AgentCore 배포 — AWS 네이티브 트레이싱
AGENTCORE_OBSERVABILITY_MODE=native           # disabled | langfuse-public | langfuse-selfhosted | native

OTEL_SERVICE_NAME=ops-ai-agent
```

## 환경별 설정 예시

### 개발 환경

```bash
# AWS
AWS_REGION=us-east-1

# Bedrock
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_TEMPERATURE=0.0

# Agent
AGENT_LANGUAGE=ko
AGENT_LOG_LEVEL=DEBUG

# Mock 모드 (실제 API 호출 없음)
CLOUDWATCH_MODE=mock
KB_MODE=mock

# Observability (로컬)
STRANDS_OBSERVABILITY_MODE=langfuse-public
```

### 프로덕션 환경

```bash
# AWS
AWS_REGION=us-east-1

# Bedrock
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_TEMPERATURE=0.0
BEDROCK_KNOWLEDGE_BASE_ID=your-kb-id     # create_kb.py 실행 후 입력

# Agent
AGENT_LANGUAGE=ko
AGENT_LOG_LEVEL=INFO

# 실제 API 사용
CLOUDWATCH_MODE=mcp
KB_MODE=mcp

# Observability (AgentCore)
AGENTCORE_OBSERVABILITY_MODE=native
OTEL_SERVICE_NAME=ops-ai-agent
```

## AWS 자격 증명

OpsAgent는 AWS 자격 증명이 필요합니다. 다음 중 하나의 방법으로 설정하세요:

### 1. 환경 변수 (권장)

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
```

### 2. AWS CLI 프로필

```bash
aws configure --profile opsagent
# .env에서 AWS_PROFILE=opsagent 설정
```

### 3. IAM 역할 (EC2/ECS)

EC2 인스턴스나 ECS 태스크에 IAM 역할을 연결하면 자동으로 자격 증명이 사용됩니다.

## 필요한 IAM 권한

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:FilterLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:Retrieve"
            ],
            "Resource": "arn:aws:bedrock:*:*:knowledge-base/*"
        }
    ]
}
```
