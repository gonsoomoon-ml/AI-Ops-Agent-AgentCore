# OpsAgent - AI Operations Agent

[Strands Agents SDK](https://strandsagents.com/) 기반 운영 자동화 AI 에이전트입니다. RAG 파이프라인으로 운영 지식을 구축하고, 자체 교정 평가 시스템으로 응답 품질을 보장하며, AWS Bedrock AgentCore로 프로덕션 배포를 지원합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| **RAG 파이프라인** | Bedrock KB + OpenSearch HYBRID 검색 + 메타데이터 카테고리 필터링 |
| **LLM 키워드 보강** | LLM 기반 BM25 키워드 최적화로 한국어 검색 정확도 향상 |
| **자체 교정 평가** | Graph 기반 5단계 파이프라인 (ANALYZE → EVALUATE → DECIDE → FINALIZE/REGENERATE) |
| **도구 연동** | CloudWatch 로그 분석, Knowledge Base Q&A (mock/mcp 전환) |
| **실시간 스트리밍** | 토큰 단위 실시간 응답 스트리밍 |
| **AgentCore 배포** | AWS Bedrock AgentCore Runtime 프로덕션 배포 |

## 개발 프로세스: Strands SDK → AgentCore

```
1. Strands Agent 개발        로컬 CLI (uv run ops-agent)
       │
2. 도구 연동 (Mock 개발)      CLOUDWATCH_MODE=mock, KB_MODE=mock (.env)
       │                      → Message Injection으로 실제 API 없이 테스트
       │
3. RAG 파이프라인 구축         데이터 변환 → LLM 보강 → S3 동기화 → 검색 평가
       │
4. 자체 교정 평가 시스템       Graph 워크플로우 (평가 → 재생성 루프)
       │
5. Observability 연동         Langfuse (로컬) / ADOT (AgentCore) 트레이싱
       │
6. AgentCore 배포             AWS Bedrock AgentCore Runtime (스트리밍)
```

### Mock 개발 & Message Injection

초기 개발 단계에서 실제 AWS API 없이 에이전트를 개발·테스트할 수 있습니다.

**도구 모드 전환** — `.env`에서 `mock` ↔ `mcp` 전환으로 테스트/운영 환경을 분리합니다.

```bash
# .env — 테스트 환경 (실제 API 호출 없음)
CLOUDWATCH_MODE=mock          # 모의 CloudWatch 데이터
KB_MODE=mock                  # 로컬 YAML 기반 KB 검색

# .env — 운영 환경 (실제 API 호출)
CLOUDWATCH_MODE=mcp           # MCP 서버 → CloudWatch API
KB_MODE=mcp                   # Bedrock KB HYBRID 검색
```

**Message Injection** — 실제 도구 호출 없이 사전 정의된 도구 결과를 주입하여 평가 시스템을 테스트합니다.

```python
mock_results = [{"tool_name": "cloudwatch_filter_log_events",
                 "tool_input": {"log_group_name": "/aws/lambda/payment"},
                 "tool_result": '{"events": [...]}'}]
response = agent.invoke_with_mock_history("분석해줘", mock_results)

# 테스트: uv run python tests/backup/test_manual.py --test 2
```

### Observability

로컬 개발과 프로덕션 배포 모두에서 트레이싱을 지원합니다. 자세한 설정은 [Observability & Langfuse](docs/setup/observability-langfuse.md)를 참고하세요.

| 환경 | 모드 | 백엔드 |
|------|------|--------|
| Strands (로컬) | `langfuse-public` | Langfuse Cloud |
| Strands (로컬) | `langfuse-selfhosted` | Self-hosted Langfuse |
| AgentCore (프로덕션) | `langfuse-public` / `langfuse-selfhosted` | Langfuse |
| AgentCore (프로덕션) | `native` | AWS ADOT → CloudWatch/X-Ray |

```bash
# .env — 로컬 개발
STRANDS_OBSERVABILITY_MODE=langfuse-public    # disabled | langfuse-public | langfuse-selfhosted

# .env — AgentCore 배포
AGENTCORE_OBSERVABILITY_MODE=native           # disabled | langfuse-public | langfuse-selfhosted | native
```

## 데이터

RAG 파이프라인에 사용되는 Q&A 데이터입니다. Synthesis data로 생성된 냉장고 기술 지원 데이터가 포함되어 있습니다.

```
data/RAG/refrigerator/              # 원본 Markdown (카테고리별 Q&A)
  ├── Diagnostics.md                #   진단/에러코드 (5E, 22E 등)
  ├── Firmware Update.md            #   펌웨어 업데이트
  ├── Glossary.md                   #   용어 사전
  └── ...                           #   총 9개 카테고리

data/RAG/refrigerator_yaml/         # 파이프라인 처리 결과
  ├── diagnostics.yaml              #   YAML 변환 결과
  ├── enriched/                     #   LLM 키워드 보강 캐시
  └── bedrock_upload/               #   S3 업로드 아티팩트 (.md + .metadata.json)
```

각 Q&A 항목은 `title`, `contents`, `category` 필드로 구성되며, 파이프라인을 통해 키워드 보강 → 메타데이터 생성 → Bedrock KB 동기화됩니다.

## RAG 파이프라인

운영 Q&A 데이터를 Bedrock KB에 적재하고, HYBRID 검색 + 메타데이터 필터링으로 정확한 답변을 제공합니다.

### 파이프라인 흐름

```
Markdown (Q&A) → YAML 변환 → LLM 키워드 보강 → Bedrock KB 생성 → S3 업로드 + 동기화 → 검색 평가
```

| 단계 | 스크립트 | 설명 |
|------|----------|------|
| 변환 | `convert_md_to_yaml.py` | Markdown Q&A → 구조화된 YAML |
| 보강 | `llm_enrich.py` | LLM이 핵심 키워드를 추출하여 BM25 검색 최적화 |
| KB 생성 | `create_kb.py` | Bedrock KB + OpenSearch + S3 인프라 생성 |
| 적재 | `prepare_and_sync.py` | 메타데이터 생성 + S3 업로드 + KB 동기화 |
| 평가 | `evaluate_retrieval.py` | Retrieve / RetrieveAndGenerate 검색 품질 측정 |

### 메타데이터 필터링

각 문서에 `category` 메타데이터를 부여하고, 검색 시 카테고리 필터를 적용하여 정확도를 높입니다.

```python
# 검색 시 카테고리 필터 적용
vector_config["filter"] = {"equals": {"key": "category", "value": "tss"}}
```

### 데이터셋

| 데이터셋 | 문서 수 | 카테고리 | 설명 |
|----------|---------|----------|------|
| **Bridge** | 157 | 9 (TSS, CMS Portal, SMF, OMC, PAI 등) | 통신 장비 운영 Q&A |
| **Refrigerator** | 107 | 9 (진단, 펌웨어, 용어, 서비스 포털 등) | 냉장고 기술 지원 Q&A (Synthesis data) |

### 자체 교정 평가 시스템

Graph 기반 워크플로우로 응답 품질을 자동 검증합니다.

```
User Query → ANALYZE (LLM + 도구 호출)
           → EVALUATE (0.0~1.0 품질 평가)
           → DECIDE (≥0.7: PASS, 0.3~0.7: REGENERATE, <0.3: BLOCK)
           → FINALIZE or REGENERATE (피드백 기반 재생성, 최대 2회)
```

## 기술 스택

| 구성요소 | 기술 |
|----------|------|
| Language | Python 3.11+ |
| LLM | AWS Bedrock Claude Sonnet 4 |
| Agent Framework | Strands Agents SDK |
| Knowledge Base | AWS Bedrock KB + OpenSearch Serverless (HYBRID 검색) |
| Embedding | Cohere Embed Multilingual v3 |
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
│       ├── cleanup.py            # 리소스 정리 (--all: 전체 삭제)
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
│   │   ├── models.py             # 평가 모델
│   │   └── checkers/             # 검사기 (CloudWatch, KB)
│   ├── tools/                    # 도구
│   │   ├── cloudwatch/           # CloudWatch 도구
│   │   └── knowledge_base/       # Knowledge Base 도구 (Bedrock KB)
│   ├── telemetry/                # 관측성 (Langfuse/OTEL)
│   │   ├── __init__.py
│   │   └── setup.py              # 관측성 설정
│   ├── prompts/                  # 시스템 프롬프트
│   └── config/                   # 설정
│
├── rag_pipeline/                  # RAG 데이터 파이프라인
│   ├── convert_md_to_yaml.py      # Markdown → YAML 변환
│   ├── llm_enrich.py              # LLM 키워드 보강 (BM25 최적화)
│   ├── prepare_and_sync.py        # 업로드 아티팩트 생성 + S3 동기화
│   ├── evaluate_retrieval.py      # 검색 품질 평가
│   ├── create_kb.py               # Bedrock KB 생성
│   └── datasets.yaml              # 데이터셋 설정
│
├── data/RAG/                      # RAG 데이터 (Synthesis data)
│   └── refrigerator/              # 냉장고 Q&A 원본 + 변환/보강 결과
│
├── docs/                          # 문서
│   ├── architecture/              # 아키텍처 (Graph, 평가, 스트리밍)
│   ├── knowledge-base/            # KB 설계, RAG 파이프라인, 연동, 평가
│   ├── setup/                     # 환경 설정, Observability
│   └── reference/                 # 연구 가이드
│
└── tests/                         # 테스트
    └── test_manual.py             # 수동 테스트 (KB 검색, 평가 워크플로우)
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
## 설정

`.env.example`을 복사하여 `.env` 파일을 생성합니다. 전체 환경 변수 상세는 [환경 설정 가이드](docs/setup/environment-configuration.md)를 참고하세요.

```bash
cp .env.example .env
vi .env
```

### 주요 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AWS_REGION` | AWS 리전 | `us-east-1` |
| `BEDROCK_MODEL_ID` | Claude 모델 ID | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `BEDROCK_TEMPERATURE` | 응답 다양성 (0.0~1.0) | `0.0` |
| `BEDROCK_MAX_TOKENS` | 최대 토큰 수 | `4096` |
| `BEDROCK_KNOWLEDGE_BASE_ID` | Bedrock KB ID | - |
| `AGENT_LANGUAGE` | 에이전트 언어 | `ko` |
| `CLOUDWATCH_MODE` | CloudWatch 도구 모드 (mock/mcp) | `mock` |
| `KB_MODE` | Knowledge Base 도구 모드 (mock/mcp) | `mock` |
| `STRANDS_OBSERVABILITY_MODE` | 로컬 관측성 모드 | `disabled` |
| `AGENTCORE_OBSERVABILITY_MODE` | AgentCore 관측성 모드 | `disabled` |


### 인프라 설정

```bash
# IAM Role, SSM Parameters 배포
./agentcore/deploy_infra.sh
```

### RAG 파이프라인

```bash
# 1. Markdown → YAML 변환
uv run python rag_pipeline/convert_md_to_yaml.py --dataset refrigerator

# 2. LLM 키워드 보강 (BM25 검색 최적화)
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator

# 3. Bedrock KB 생성 (S3 + OpenSearch + KB — 최초 1회, 업로드+동기화 포함)
uv run python rag_pipeline/create_kb.py --dataset refrigerator --mode create
#    → 스크립트 완료 후 출력된 값을 rag_pipeline/datasets.yaml에 수동 입력:
#      s3_bucket: "ops-fridge-kb-xxxx"
#      kb_id: "XXXXXXXXXX"
#      ds_id: "XXXXXXXXXX"
#    → .env에 KB ID 설정 (에이전트가 KB 검색을 사용하려면 필수):
#      BEDROCK_KNOWLEDGE_BASE_ID=XXXXXXXXXX

# 4. 검색 품질 평가
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --rag  # RetrieveAndGenerate

# (데이터 수정 후 재동기화 시에만 실행)
# uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode prepare
# uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode sync
```

### 실행 및 테스트 (로컬)

**로컬 실행** — 대화형 CLI로 자유롭게 질문

```bash
uv run ops-agent                   # 대화형 CLI (CloudWatch, KB 등 모든 질문)
uv run python -m ops_agent.main --prompt "TSS Activation이 뭐야?"  # 단일 프롬프트
```

```
> payment-service에서 최근 1시간 동안 ERROR 로그 보여줘
> TSS Activation이 뭐야?
> CMS 포털에서 Role 권한 받는 방법
```

**수동 테스트** — 사전 정의된 시나리오로 기능 검증

```bash
uv run python tests/test_manual.py             # 테스트 목록 확인
uv run python tests/test_manual.py --test 1    # KB 검색 (평가 없음)
uv run python tests/test_manual.py --test 2    # KB + Graph 평가 워크플로우
```

### AgentCore 배포

```bash
cd agentcore

# 에이전트 배포
uv run python scripts/deploy.py --auto-update

# 테스트
uv run python scripts/invoke.py --test simple

# 대화형 모드
uv run python scripts/invoke.py --interactive
```

### 리소스 정리 (Cleanup)

```bash
cd agentcore

# 기본 정리 (AgentCore 런타임, SSM 파라미터, ECR 리포지토리)
uv run python scripts/cleanup.py

# 옵션: ECR 또는 SSM 유지
uv run python scripts/cleanup.py --keep-ecr
uv run python scripts/cleanup.py --keep-ssm

# 모든 리소스 삭제 (런타임 + KB + CodeBuild + CloudFormation + 로그 그룹)
uv run python scripts/cleanup.py --all

# 확인 프롬프트 생략
uv run python scripts/cleanup.py --all -f
```

| 모드 | 삭제 대상 |
|------|-----------|
| 기본 | AgentCore 런타임, SSM (runtime_arn/id), ECR, 로컬 메타데이터 |
| `--all` | 위 항목 + Knowledge Base (OpenSearch, S3), CodeBuild (프로젝트, IAM, S3), CloudWatch 로그 그룹, CloudFormation 스택, 로컬 파일 |


## 문서

| 문서 | 설명 |
|------|------|
| **Architecture** | |
| [Graph 워크플로우](docs/architecture/graph-workflow.md) | 평가 그래프 설계 및 구현 |
| [평가 시스템 설계](docs/architecture/evaluation-design.md) | 응답 품질 평가 시스템 |
| [스트리밍 구현](docs/architecture/streaming-implementation.md) | 실시간 스트리밍 아키텍처 |
| **Knowledge Base** | |
| [데이터 가이드](docs/knowledge-base/data-guide.md) | Q&A 데이터 구조 및 처리 과정 (Synthesis data) |
| [RAG Knowledge Base 설계](docs/knowledge-base/rag-knowledge-base-design.md) | Bedrock KB + OpenSearch 설계 |
| [RAG 파이프라인](docs/knowledge-base/rag-pipeline.md) | RAG 데이터 파이프라인 (enrich → sync → evaluate) |
| [KB Agent 연동](docs/knowledge-base/kb-agent-integration.md) | Bedrock KB 도구 연동 (Bridge/Refrigerator) |
| [KB 평가 시스템](docs/knowledge-base/kb-evaluation.md) | KBChecker 평가 설계 및 테스트 |
| **Setup** | |
| [환경 설정 가이드](docs/setup/environment-configuration.md) | 환경 변수 및 .env 설정 |
| [Observability & Langfuse](docs/setup/observability-langfuse.md) | Langfuse 통합 및 관측성 설정 |
| **Reference** | |
| [연구 가이드 결과](docs/reference/research-guide-results.md) | Strands SDK 연구 및 패턴 |

## 참고 자료

- [Strands Agents SDK](https://strandsagents.com/)
- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Self-Correcting Translation Agent](https://github.com/gonsoomoon-ml/Self-Correcting-Explainable-Translation-Agent)

## 라이선스

MIT License
