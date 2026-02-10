# KB Agent Integration

> Strands Agent에 Bedrock Knowledge Base 도구 연동
> 작성일: 2026-02-10

---

## 목차

1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [파일 구조](#3-파일-구조)
4. [설정](#4-설정)
5. [KB Tool 상세](#5-kb-tool-상세)
6. [시스템 프롬프트](#6-시스템-프롬프트)
7. [AgentCore 배포](#7-agentcore-배포)
8. [테스트](#8-테스트)
9. [카테고리 목록](#9-카테고리-목록)

---

## 1. 개요

Strands Agent가 Bedrock Knowledge Base를 실시간으로 검색하여 기술 문서 기반 답변을 제공합니다.

- **검색 방식**: HYBRID (벡터 + BM25 키워드) 검색
- **임베딩 모델**: `cohere.embed-multilingual-v3` (한국어 최적)
- **도구 패턴**: CloudWatch와 동일한 Factory 패턴 (mock/mcp 모드 전환)
- **지원 KB**: Bridge (TSS/CMS/SMF/OMC/PAI), Refrigerator

## 2. 아키텍처

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────────┐
│  OpsAgent (Strands Agent)                   │
│                                             │
│  tools: [cloudwatch, kb_retrieve]           │
│                                             │
│  1. 질문 분석 → kb_retrieve 도구 선택       │
│  2. category 결정 (예: "tss")               │
│  3. kb_retrieve(query, category) 호출       │
│  4. 검색 결과 기반 답변 생성                │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │ KB_MODE=mock        │ KB_MODE=mcp
        ▼                     ▼
┌───────────────┐   ┌──────────────────────┐
│ mock_tools.py │   │ kb_tools.py          │
│ (로컬 YAML)   │   │ (Bedrock Retrieve)   │
└───────────────┘   └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Bedrock KB (HYBRID)  │
                    │ OpenSearch Serverless│
                    │ cohere.embed-v3      │
                    └──────────────────────┘
```

## 3. 파일 구조

```
src/ops_agent/tools/knowledge_base/
├── __init__.py       # Factory: get_kb_tools() → mock 또는 bedrock
├── kb_tools.py       # Bedrock Retrieve API (KB_MODE=mcp)
├── mock_tools.py     # 로컬 YAML 검색 (KB_MODE=mock)
└── data_loader.py    # YAML 검색 엔진 (mock_tools에서 사용)
```

### Tool Factory 패턴

`__init__.py`는 **Tool Factory** 역할을 합니다. Tool Factory란 런타임 설정에 따라 적절한 도구 구현체를 선택·반환하는 모듈입니다. 호출하는 쪽은 어떤 백엔드가 사용되는지 알 필요 없이 팩토리만 호출하면 됩니다.

**동작 흐름:**

```
get_kb_tools()
    │
    ├─ Settings에서 KB_MODE 읽기
    │
    ├─ KB_MODE=mock  → mock_tools.get_mock_tools() lazy import → 로컬 YAML 도구 반환
    ├─ KB_MODE=mcp   → kb_tools.get_kb_tools() lazy import    → Bedrock KB 도구 반환
    └─ 그 외         → ValueError
```

**핵심 설계:**

- **Lazy import** — 선택된 모드의 모듈만 import합니다. mock 모드에서는 boto3가 로드되지 않고, mcp 모드에서는 YAML 엔진이 로드되지 않습니다.
- **단일 진입점** — 호출하는 쪽은 `get_kb_tools()`만 호출하면 되므로 조건 분기가 필요 없습니다:

```python
# agent/ops_agent.py — 모드에 관계없이 동일한 코드
from ops_agent.tools.knowledge_base import get_kb_tools

agent = Agent(tools=get_kb_tools())  # mock이든 mcp이든 동일
```

- **확장 용이** — 새 백엔드 추가 시 `__init__.py`에 `elif` 한 줄만 추가하면 됩니다.
- **일관된 패턴** — CloudWatch (`tools/cloudwatch/__init__.py`)와 동일한 구조로, 모든 도구 모듈이 같은 방식으로 작동합니다.

### 변경된 파일

| 파일 | 변경 내용 |
|------|-----------|
| `.env` | `KB_MODE=mcp`, `BEDROCK_KNOWLEDGE_BASE_ID` 추가 |
| `config/settings.py` | `kb_mode`, `bedrock_knowledge_base_id` (기존) |
| `agent/ops_agent.py` | `get_kb_tools()` import 및 tools 등록 |
| `graph/nodes.py` | `get_kb_tools()` import 및 tools 등록 |
| `prompts/ops_agent_ko.md` | KB 도구 설명 + 카테고리 목록 + 사용 가이드 |
| `prompts/ops_agent_en.md` | 동일 (영문) |
| `tests/test_manual.py` | 테스트 8 (KB 검색) 추가 |
| `agentcore/scripts/deploy.py` | KB env vars를 AgentCore에 전달 |
| `agentcore/cloudformation/infrastructure.yaml` | `bedrock:Retrieve` IAM 권한 추가 |

## 4. 설정

### .env

```bash
# Knowledge Base
BEDROCK_KNOWLEDGE_BASE_ID=G5GG6ZV8GX  # Bridge KB
# KB_MODE=mock                          # 로컬 YAML (테스트용)
KB_MODE=mcp                            # Bedrock API (운영)
```

### KB 정보 (datasets.yaml)

| Dataset | KB ID | DS ID | S3 Bucket | Entries |
|---------|-------|-------|-----------|---------|
| Bridge | `G5GG6ZV8GX` | `ZQUUKFZVSU` | `ops-bridge-kb-fc4e` | 157 |
| Refrigerator | `XANPGITYE3` | `C0IFPMQ3SP` | `ops-fridge-kb-v2-3432` | 107 |

KB 전환 시 `.env`의 `BEDROCK_KNOWLEDGE_BASE_ID` 값만 변경하면 됩니다.

## 5. KB Tool 상세

### kb_retrieve

```python
@tool
def kb_retrieve(
    query: str,       # 검색 질문
    category: str,    # 카테고리 필터 (필수)
    num_results: int = 5,
) -> str:             # JSON 결과
```

**특징:**
- `category`가 필수 파라미터 — 메타데이터 필터링으로 검색 정확도 향상
- HYBRID 검색 (`overrideSearchType: "HYBRID"`) — 한국어 BM25 + 벡터
- 싱글톤 boto3 클라이언트 (lazy init)
- 에러 시 JSON 에러 응답 반환 (exception 아님)

**반환 JSON:**

```json
{
  "status": "success",
  "mode": "bedrock",
  "kb_id": "G5GG6ZV8GX",
  "query": "TSS Activation이 뭐야?",
  "result_count": 5,
  "results": [
    {
      "doc_id": "tss-001",
      "score": 0.6885,
      "category": "tss",
      "content": "# TSS Activation에 대한 설명\n..."
    }
  ]
}
```

## 6. 시스템 프롬프트

에이전트가 KB 도구를 올바르게 사용하도록 시스템 프롬프트에 다음을 포함:

- **도구 설명**: `kb_retrieve` 파라미터 및 사용법
- **카테고리 목록**: Bridge/Refrigerator 전체 카테고리 나열
- **사용 가이드**:
  - 기술 용어, 에러 코드, 포털 사용법 질문 → `kb_retrieve` 사용
  - 카테고리 불명 시 `glossary`로 먼저 검색
  - 검색 결과 content를 요약하지 말고 그대로 전달

## 7. AgentCore 배포

### IAM 권한

`infrastructure.yaml`에 추가된 권한:

```yaml
- Sid: BedrockKBRetrieve
  Effect: Allow
  Action:
    - bedrock:Retrieve
  Resource:
    - 'arn:aws:bedrock:*:*:knowledge-base/*'
```

### 배포 순서

```bash
# 1. IAM 역할 업데이트
cd agentcore && ./deploy_infra.sh

# 2. AgentCore 배포 (KB env vars 자동 포함)
uv run python scripts/deploy.py --auto-update

# 3. 테스트
uv run python scripts/invoke.py --prompt "TSS Activation이 뭐야?"
```

`deploy.py`가 `.env`에서 `KB_MODE`와 `BEDROCK_KNOWLEDGE_BASE_ID`를 읽어 AgentCore 환경 변수로 전달합니다.

## 8. 테스트

### 로컬 테스트

```bash
# test_manual.py (테스트 8)
uv run python tests/test_manual.py --test 8

# 직접 호출
uv run python -c "
from ops_agent.agent import OpsAgent
agent = OpsAgent(enable_evaluation=False)
agent.invoke('TSS Activation이 뭐야?')
"
```

### AgentCore 테스트

```bash
cd agentcore

# 단일 질문
uv run python scripts/invoke.py --prompt "TSS Activation이 뭐야?"
uv run python scripts/invoke.py --prompt "CMS 포털에서 Role 권한 받는 방법"
uv run python scripts/invoke.py --prompt "P4 업로드 에러 4000 해결 방법"

# 대화형
uv run python scripts/invoke.py --interactive
```

### RAG 파이프라인 평가 (검색 정확도)

```bash
# Retrieve 검색 정확도
uv run python rag_pipeline/evaluate_retrieval.py --dataset bridge

# RetrieveAndGenerate (LLM 답변 포함)
uv run python rag_pipeline/evaluate_retrieval.py --dataset bridge --rag
```

## 9. 카테고리 목록

### Bridge (9 categories, 157 entries)

| Category | 설명 |
|----------|------|
| `tss` | TSS Activation, TSS 2.0/2.1 |
| `cms_portal` | CMS Portal 사용법, P4 업로드 |
| `pai_portal` | PAI Portal 앱 설치, CTS 에러 |
| `app_delivery` | App Delivery 제공 방식 |
| `omc_update` | OMC Customization |
| `grasse_portal` | Grasse Portal 접속 |
| `smf` | SIM Mobility Framework |
| `client` | 단말 로그 확보 |
| `glossary` | 용어 정의 (TSS, Bridge 등) |

### Refrigerator (9 categories, 107 entries)

| Category | 설명 |
|----------|------|
| `diagnostics` | 에러 코드, 자가진단 |
| `firmware_update` | OTA 펌웨어 업데이트 |
| `glossary` | 용어 정의 (인버터, 냉매 등) |
| `model_matching` | 모델번호 체계, 부품 호환성 |
| `product_line` | 제품군 (양문형, 김치냉장고 등) |
| `service_portal` | 서비스 포털 사용법 |
| `smart_feature` | AI Energy, 식품관리 카메라 등 |
| `smartthings_portal` | SmartThings 연동 |
