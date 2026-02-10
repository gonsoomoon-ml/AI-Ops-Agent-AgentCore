# RAG Pipeline

> Bedrock Knowledge Base 데이터 준비 파이프라인
> 작성일: 2026-02-08

---

## 목차

1. [개요](#1-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [파이프라인 단계](#3-파이프라인-단계)
4. [datasets.yaml 설정](#4-datasetsyaml-설정)
5. [Step 1: Markdown → YAML 변환](#5-step-1-markdown--yaml-변환)
6. [Step 2: LLM Enrichment](#6-step-2-llm-enrichment)
7. [Step 3: Bedrock KB 생성](#7-step-3-bedrock-kb-생성)
8. [Step 4: Bedrock KB 준비 및 동기화](#8-step-4-bedrock-kb-준비-및-동기화)
9. [Step 5: 검색 정확도 평가](#9-step-5-검색-정확도-평가)
10. [Enrichment 프롬프트 설계](#10-enrichment-프롬프트-설계)
11. [성능 결과](#11-성능-결과)
12. [새 데이터셋 추가 방법](#12-새-데이터셋-추가-방법)

---

## 1. 개요

Raw markdown Q&A 데이터를 Bedrock Knowledge Base에 최적화된 형태로 변환하는 5단계 파이프라인.

```
Raw MD → YAML → LLM Enrichment → Bedrock KB 생성 → 준비/동기화 → 정확도 평가
```

핵심 설계 원칙:
- **1 Q&A 엔트리 = 1 문서** (청킹 없음 — 엔트리가 이미 자기 완결적 의미 단위)
- **HYBRID 검색** (벡터 유사도 + BM25 키워드 매칭) 최적화
- **LLM enrichment**로 BM25 성능 극대화 (regex 대비 +1.4% Top-1 정확도)
- **다중 데이터셋** 지원 (`datasets.yaml`로 설정 관리)

## 2. 디렉토리 구조

```
AI-Ops-Agent-AgentCore/
├── rag_pipeline/                          # 파이프라인 스크립트
│   ├── datasets.yaml                      # 데이터셋 레지스트리
│   ├── convert_md_to_yaml.py              # Markdown → YAML 변환
│   ├── llm_enrich.py                      # LLM 키워드 보강 (BM25 최적화)
│   ├── create_kb.py                       # Bedrock KB 생성 (첫 회)
│   ├── prepare_and_sync.py                # 업로드 아티팩트 생성 + S3 동기화
│   └── evaluate_retrieval.py              # 검색 품질 평가
│
├── data/RAG/
│   ├── refrigerator/                      # Raw MD (9 카테고리)
│   ├── refrigerator_yaml/                 # 변환된 YAML
│   │   ├── index.yaml                     # 카테고리 인덱스
│   │   ├── diagnostics.yaml               # 카테고리별 YAML
│   │   ├── glossary.yaml
│   │   ├── ...
│   │   ├── enriched/                      # LLM enrichment 캐시 (JSON)
│   │   │   ├── glossary-001.json
│   │   │   ├── glossary-002.json
│   │   │   └── ...
│   │   └── bedrock_upload/                # 빌드 산출물 (.md + .metadata.json)
│   │       ├── diagnostics-001.md
│   │       ├── diagnostics-001.md.metadata.json
│   │       └── ...
│
└── src/ops_agent/prompts/
    └── kb_enrichment.md                   # LLM enrichment 프롬프트 템플릿 (v3)
```

## 3. 파이프라인 단계

```
Step 1                Step 2               Step 3              Step 4                Step 5
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────────┐    ┌───────────────┐
│ Raw .md  │───▶│  YAML 변환   │───▶│LLM Enrichment │───▶│ Bedrock KB 생성 │───▶│ 준비 + 동기화 │───▶ 정확도 평가
│ (수동)   │    │ (regex 기반) │    │(Claude Sonnet)│    │ (첫 회 1회)     │    │ (이후 반복)   │
└──────────┘    └──────────────┘    └───────────────┘    └─────────────────┘    └───────────────┘
                 keywords 추출         핵심 용어 추출        S3 + OpenSearch       .md + .metadata.json
                 에러 코드 추출        8개 질문 변형          + KB + DataSource     S3 업로드 + 인덱싱
                 질문 변형 생성        구별적 명사/키워드     (업로드+동기화 포함)
```

전체 실행 (첫 회):

```bash
# Step 1: Markdown → YAML
uv run python rag_pipeline/convert_md_to_yaml.py --dataset refrigerator

# Step 2: LLM Enrichment (Claude API 호출 — 107 entries ≈ 2분)
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator

# Step 3a: Bedrock 업로드용 파일 생성
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode prepare

# Step 3b: Bedrock KB 생성 + S3 업로드 + 동기화 (첫 회 1회)
uv run python rag_pipeline/create_kb.py --dataset refrigerator --mode create

# Step 4: 검색 정확도 평가 (동기화 후 ~60초 대기 필요)
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator
```

이후 데이터 업데이트 시 (KB 이미 존재):

```bash
# 변환 + 업로드 + 동기화
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator

# 또는 단계별로:
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode prepare
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode sync
```

## 4. datasets.yaml 설정

모든 스크립트는 `rag_pipeline/datasets.yaml`에서 데이터셋별 설정을 로드함.

```yaml
datasets:
  refrigerator:
    name: "Samsung Refrigerator Q&A"
    description: "삼성 냉장고 진단, 펌웨어, 용어, 서비스 포털 등 Q&A"
    raw_dir: "data/RAG/refrigerator"         # Raw MD 경로
    yaml_dir: "data/RAG/refrigerator_yaml"   # YAML 출력 경로
    # Bedrock KB — create_kb.py 실행 후 아래 값을 업데이트
    s3_bucket: ""           # create_kb.py 출력값 입력
    kb_id: ""               # create_kb.py 출력값 입력
    ds_id: ""               # create_kb.py 출력값 입력
    kb_name: "ops-fridge-kb"
    embedding_model: "amazon.titan-embed-text-v2:0"
    # LLM enrichment
    stop_words: "냉장고, 삼성, 제품, 기능, 설정, ..."
    # 카테고리 표시명 (English → Korean)
    category_names:
      Diagnostics: "진단/에러코드"
      Glossary: "용어 사전"
      ...
```

핵심 필드:

| 필드 | 용도 | 사용 스크립트 |
|------|------|-------------|
| `raw_dir` | Raw MD 파일 위치 | convert_md_to_yaml.py |
| `yaml_dir` | YAML 출력 + enrichment 캐시 위치 | 전체 |
| `kb_name` | Bedrock KB 이름 | create_kb.py |
| `embedding_model` | 임베딩 모델 ID | create_kb.py |
| `s3_bucket`, `kb_id`, `ds_id` | Bedrock KB 리소스 (create_kb.py 실행 후 설정) | prepare_and_sync.py, evaluate_retrieval.py |
| `stop_words` | LLM enrichment 금지어 (고빈도 공통 단어) | llm_enrich.py |
| `category_names` | 카테고리 한국어 표시명 | prepare_and_sync.py |

## 5. Step 1: Markdown → YAML 변환

```bash
uv run python rag_pipeline/convert_md_to_yaml.py --dataset refrigerator
```

### 입력: Raw Markdown

카테고리별 `.md` 파일 (예: `data/RAG/refrigerator/Diagnostics.md`):

```markdown
**title**: 냉장고 문제 발생 시 에러 코드 확인 방법
---
- **contents**: 냉장고에 문제가 발생하면 제어 패널 디스플레이에...
- **urls**: https://www.samsung.com/sec/support/
- sheet: Diagnostics
- row: 2
- generated_at: 2026-02-08T10:00:00
```

### 출력: 구조화된 YAML

카테고리별 YAML + 인덱스:

```yaml
# data/RAG/refrigerator_yaml/diagnostics.yaml
category_id: diagnostics
category_name: Diagnostics
entry_count: 5
entries:
  - id: diagnostics-001
    title: "냉장고 문제 발생 시 에러 코드 확인 방법"
    answer: "냉장고에 문제가 발생하면..."
    error_codes: ["5E", "22E"]
    keywords: ["에러 코드", "SmartThings", ...]
    question_variants: ["에러 코드 확인이 뭐야?", ...]
```

### 처리 내용

- **에러 코드 추출**: `\b\d{1,3}[A-Z]\b` 패턴 (예: 5E, 22E, 84C)
- **키워드 추출**: 영어 기술 용어, 괄호 안 용어, 한국어 기술 명사
- **질문 변형 생성**: 제목 패턴에 따른 regex 기반 변형 (2~5개)
- **결정적 ID 생성**: `{category_id}-{순번:03d}` (예: `diagnostics-001`)

## 6. Step 2: LLM Enrichment

```bash
# 전체 enrichment (캐시에 없는 항목만 처리)
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator

# 강제 재생성 (캐시 무시)
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --force

# 특정 카테고리만
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --category glossary

# dry-run (프롬프트만 확인, API 호출 없음)
uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --dry-run
```

### 왜 LLM Enrichment가 필요한가

HYBRID 검색에서 BM25 컴포넌트는 **핵심 용어의 반복 출현 빈도**로 문서를 랭킹함. Regex 기반 변형은:
- 영어 용어가 없는 제목에서 변형 수가 부족 (4개 vs 8개)
- QnA 형식 제목 (`QnA. SmartThings 앱에서...`)에서 핵심 용어 추출 실패
- 구별력 없는 공통 명사 (냉장고, 삼성, 서비스)를 포함

LLM v3 enrichment는 이 문제를 해결:
- **항상 8개** 질문 변형 (고정 템플릿 사용)
- QnA/문장 형태 제목에서도 정확한 핵심 용어 추출
- 구별적 명사만 선별 (stop_words + 형제 항목 대조)

### 출력: Enrichment 캐시

`data/RAG/refrigerator_yaml/enriched/glossary-003.json`:

```json
{
  "ko_core_term": "냉매",
  "en_core_term": "Refrigerant",
  "ko_nouns": ["R-600a", "이소부탄", "오존층파괴지수", "지구온난화지수",
               "증발기", "응축기", "냉매누출", "화학물질"],
  "question_variants": [
    "냉매 알려줘",
    "냉매에 대해 설명해줘",
    "냉매가 뭐야?",
    "냉매 뭐야?",
    "Refrigerant이 뭐야?",
    "Refrigerant 설명해줘",
    "냉매(Refrigerant) 설명해줘",
    "냉매(Refrigerant)가 무엇인가요"
  ],
  "search_keywords": ["GWP", "ODP", "Refrigerant", "응축기", "이소부탄",
                       "증발기", "R-600a", "냉매", "오존층파괴지수",
                       "지구온난화지수", "냉매누출", "열흡수"]
}
```

### 핵심 설계: "LLM decides WHAT, templates decide HOW"

| 역할 | LLM (의미 이해) | 고정 템플릿 (BM25 최적화) |
|------|----------------|------------------------|
| 핵심 용어 | ko_core_term 추출 (조사 제거) | 8개 변형에 모두 포함 |
| 영어 용어 | en_core_term 추출 | 5~8번 변형에 사용 |
| 구별적 명사 | stop_words + 형제 항목 대조 | blockquote에 배치 |
| 키워드 확장 | 고유 기술 용어 2~3개 추가 | 기존 키워드 전부 유지 |

질문 변형 템플릿 (8개 고정):

```
1. {KO} 알려줘
2. {KO}에 대해 설명해줘
3. {KO}가 뭐야?
4. {KO} 뭐야?
5. {EN}이 뭐야?     (EN 없으면: {KO} 어떻게 해?)
6. {EN} 설명해줘    (EN 없으면: {KO} 알려주세요)
7. {KO}({EN}) 설명해줘  (EN 없으면: {KO}이 뭔가요?)
8. {KO}({EN})가 무엇인가요  (EN 없으면: {KO} 무엇인가요?)
```

### 모델 및 비용

- 모델: `claude-sonnet-4-5` (Bedrock cross-region inference)
- 1 엔트리 ≈ 1K input + 0.3K output tokens
- 107 엔트리 ≈ 2분, ~$0.15
- 캐시 사용: 이미 처리된 엔트리는 `--force` 없이 스킵

## 7. Step 3: Bedrock KB 생성

```bash
# KB 생성 (S3 버킷 + OpenSearch 컬렉션 + Bedrock KB + 데이터 소스 + 업로드 + 동기화)
uv run python rag_pipeline/create_kb.py --dataset refrigerator --mode create

# KB 삭제
uv run python rag_pipeline/create_kb.py --dataset refrigerator --mode delete
```

> **전제조건**: Step 3a(`prepare_and_sync.py --mode prepare`)로 `bedrock_upload/` 산출물이 먼저 생성되어 있어야 함.

### 생성 과정

`create_kb.py --mode create`는 다음을 한 번에 수행:

1. **IAM 역할** 생성 (Bedrock KB 실행용)
2. **S3 버킷** 생성 (데이터 소스 저장소)
3. **OpenSearch Serverless 컬렉션** 생성 (벡터 스토어)
4. **OpenSearch 인덱스** 생성 — `keyword` 서브필드 포함 (메타데이터 필터링용)
5. **Bedrock KB** 생성 + **DataSource** 생성 (NONE 청킹)
6. `bedrock_upload/` 디렉토리의 파일을 **S3에 업로드**
7. **인덱싱 작업** 시작 (동기화)
8. **SSM Parameter Store**에 KB ID 저장

### OpenSearch 인덱스 매핑

기본 `KnowledgeBasesForAmazonBedrock` 클래스를 확장하여 `keyword` 서브필드를 추가:

```json
{
  "category": {
    "type": "text",
    "fields": {
      "keyword": { "type": "keyword", "ignore_above": 256 }
    }
  }
}
```

이 매핑이 없으면 Bedrock 메타데이터 필터(`category.keyword` 쿼리)가 아무 결과도 반환하지 않음.

### 생성 후 필수 작업

스크립트 실행 후 출력된 값을 `datasets.yaml`에 업데이트:

```yaml
s3_bucket: "ops-fridge-kb-xxxxx"   # 출력된 S3 버킷명
kb_id: "XXXXXXXXXX"                 # 출력된 KB ID
ds_id: "XXXXXXXXXX"                 # 출력된 DataSource ID
```

이 값이 설정되어야 `prepare_and_sync.py --mode sync`와 `evaluate_retrieval.py`가 작동함.

## 8. Step 4: Bedrock KB 준비 및 동기화

KB가 이미 존재하는 상태에서 데이터를 업데이트할 때 사용.

```bash
# 전체 (변환 + 업로드 + 동기화)
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator

# 변환만 (로컬 파일 생성, S3 업로드 없음)
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode prepare

# 업로드 + 동기화만 (이미 변환된 파일)
uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode sync
```

### 변환 과정

각 YAML 엔트리를 2개 파일로 변환:

**1. 보강 Markdown** (`diagnostics-001.md`):

```markdown
# 냉장고 문제 발생 시 에러 코드 확인 방법

> 에러 코드 확인, Error Code, 제어패널, 디스플레이, 5E, 22E, 진단/에러코드

## 관련 질문
- 에러 코드 확인 알려줘
- 에러 코드 확인에 대해 설명해줘
- 에러 코드 확인가 뭐야?
- 에러 코드 확인 뭐야?
- Error Code이 뭐야?
- Error Code 설명해줘
- 에러 코드 확인(Error Code) 설명해줘
- 에러 코드 확인(Error Code)가 무엇인가요

## 답변
냉장고에 문제가 발생하면 제어 패널 디스플레이에...

## 핵심 키워드
에러 코드, SmartThings, 제어 패널, 디스플레이, ...
```

구조 설계:
- `# 제목` — 벡터 임베딩에서 가장 높은 가중치
- `> blockquote` — 핵심 용어 + 구별적 명사 + 에러 코드 + 카테고리명
- `## 관련 질문` — BM25 용어 빈도 극대화 (핵심 용어가 8회 반복)
- `## 답변` — 원본 컨텐츠
- `## 핵심 키워드` — 추가 검색어

**2. 메타데이터 JSON** (`diagnostics-001.md.metadata.json`):

```json
{
  "metadataAttributes": {
    "doc_id": "diagnostics-001",
    "category": "diagnostics",
    "document_type": "qa",
    "has_error_codes": true,
    "error_codes": "5E, 22E",
    "keywords_ko": "에러 코드, SmartThings, 제어 패널, ..."
  }
}
```

메타데이터 제약:
- `id` 키 사용 불가 (예약어) → `doc_id` 사용
- 빈 문자열 값 불가 → 없으면 필드 자체를 생략
- `has_error_codes`는 boolean (문자열 `"false"` 불가)
- 파일명: `<source>.md.metadata.json` (`.metadata.json`이 아님)

### S3 업로드 및 KB 동기화

1. 기존 S3 객체 전부 삭제
2. 새 `.md` + `.metadata.json` 파일 업로드
3. `start_ingestion_job` API로 KB 인덱싱 시작
4. 완료까지 폴링 (약 1~2분)

> **중요**: 동기화 완료 후 OpenSearch에 데이터가 전파되기까지 **~60초 대기** 필요. 즉시 쿼리하면 부정확한 결과가 나올 수 있음.

## 9. Step 5: 검색 정확도 평가

```bash
# Retrieve 검색 정확도 평가
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --verbose
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --filter
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --category glossary

# RetrieveAndGenerate (RAG) — LLM 답변 포함 테스트
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --rag
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --rag --query "에러코드 22E가 뭐야?"
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --rag --category diagnostics
uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --rag --limit 2
```

### CLI 옵션

| 옵션 | 설명 |
|------|------|
| `--dataset` | 데이터셋 이름 (기본값: refrigerator) |
| `--verbose` | 상세 출력 (top-3 결과 표시) |
| `--category` | 특정 카테고리만 테스트 |
| `--filter` | 카테고리 메타데이터 필터 적용 |
| `--rag` | RetrieveAndGenerate 모드 (LLM 답변 포함) |
| `--query` | 단일 질문 (`--rag`와 함께 사용) |
| `--limit` | 카테고리당 최대 테스트 수 (`--rag`와 함께 사용) |

### 테스트 케이스 구조

```python
TEST_CASES = [
    # (쿼리, 정답_doc_id, 카테고리, 설명)
    ("에러 코드 22E가 뭐야?",
     ["diagnostics-002", "diagnostics-001"], "diagnostics",
     "에러 코드 의미 질문 (22E)"),
    ...
]
```

58개 테스트 케이스:
- 9개 카테고리 × 5~10개 쿼리
- cross-category 모호한 질문 3개
- 각 케이스에 1개 이상의 정답 doc_id

### 평가 지표

| 지표 | 의미 |
|------|------|
| **Top-1** | 첫 번째 결과가 정답 |
| **Top-3** | 상위 3개 중 정답 포함 |
| **Top-5** | 상위 5개 중 정답 포함 |

카테고리별 Top-1 정확도와 실패 목록을 출력.

### RetrieveAndGenerate (RAG) 모드

`--rag` 모드는 Bedrock `RetrieveAndGenerate` API를 사용하여 검색 + LLM 답변 생성을 함께 테스트:

- 커스텀 `promptTemplate` 적용 (상세 답변 유도, `$search_results$` 변수 필수)
- 추론 프로필 ARN에 계정 ID 포함 필요 (`us.*` 프로필 사용, `global.*`은 불가)
- `--query "질문"`으로 단일 질문 대화형 테스트 가능

## 10. Enrichment 프롬프트 설계

프롬프트 파일: `src/ops_agent/prompts/kb_enrichment.md`

`PromptTemplateLoader`를 사용하여 YAML frontmatter + `{{ variable }}` 구문으로 관리.

### 템플릿 변수

| 변수 | 출처 | 설명 |
|------|------|------|
| `{{ title }}` | YAML entry | 제목 |
| `{{ category }}` | YAML entry | 카테고리 이름 |
| `{{ answer }}` | YAML entry | 답변 (1500자 제한) |
| `{{ keywords }}` | YAML entry | 기존 추출된 키워드 |
| `{{ error_codes }}` | YAML entry | 에러 코드 목록 |
| `{{ siblings }}` | 같은 카테고리 항목들 | 형제 항목 제목 (최대 10개) |
| `{{ total_docs }}` | 전체 엔트리 수 | 문서 총 개수 |
| `{{ stop_words }}` | datasets.yaml | 도메인별 고빈도 공통 단어 |

### 프롬프트 버전 이력

| 버전 | 접근 방식 | Top-1 | 실패 원인 |
|------|----------|-------|----------|
| Regex | 패턴 매칭 + 고정 변형 | 90.0% | QnA 제목 파싱 실패, 변형 수 부족 |
| LLM v1 | 자유 변형 5개 | 79.0% | 공통 키워드 오염 → 크로스 문서 간섭 |
| LLM v2 | 구별적 변형 5개 | 65.5% | 자연스러운 다양한 변형이 BM25 빈도 희석 |
| **LLM v3** | **고정 템플릿 8개 + LLM 용어 추출** | **91.4%** | **BM25 빈도 유지 + LLM 의미 품질** |

핵심 교훈:
- BM25는 용어 빈도(TF)에 민감 → 짧고 반복적인 변형이 유리
- LLM의 "자연스럽고 다양한" 출력은 BM25를 약화시킴
- **해결**: LLM은 WHAT (정확한 핵심 용어)만 결정, HOW (반복 구조)는 고정 템플릿이 결정

## 11. 성능 결과

### Refrigerator 데이터셋 (107 docs, 58 test cases)

| 설정 | Top-1 | Top-3 |
|------|-------|-------|
| Basic .md (벡터 전용) | 69% | 91% |
| + HYBRID 검색 | 81% | 100% |
| + Regex enrichment | 90% (52/58) | 100% |
| + 메타데이터 필터 | 90% (52/58) | 100% |
| **+ LLM v3 enrichment** | **91.4% (53/58)** | **100%** |

### Bedrock KB 설정

| 항목 | 값 |
|------|-----|
| 임베딩 모델 | Cohere Embed Multilingual v3 (1,024 dim) |
| 검색 방식 | HYBRID (벡터 + BM25) |
| 벡터 스토어 | OpenSearch Serverless |
| 청킹 | NONE (1 엔트리 = 1 문서) |

## 12. 새 데이터셋 추가 방법

### 1단계: datasets.yaml에 등록

```yaml
datasets:
  new_dataset:
    name: "New Dataset Name"
    raw_dir: "data/RAG/new_dataset"
    yaml_dir: "data/RAG/new_dataset_yaml"
    s3_bucket: ""       # create_kb.py 실행 후 설정
    kb_id: ""           # create_kb.py 실행 후 설정
    ds_id: ""           # create_kb.py 실행 후 설정
    kb_name: "ops-new-dataset-kb"
    embedding_model: "amazon.titan-embed-text-v2:0"
    stop_words: ""      # 2단계 이후 설정
    category_names: {}  # 1단계 이후 설정
```

### 2단계: Raw MD 준비 및 YAML 변환

```bash
# data/RAG/new_dataset/ 에 카테고리별 .md 파일 배치
uv run python rag_pipeline/convert_md_to_yaml.py --dataset new_dataset
```

카테고리 수와 엔트리 수를 확인한 후, `datasets.yaml`에 `category_names`를 설정.

### 3단계: Stop words 분석 및 LLM enrichment

데이터 전체에서 **고빈도 공통 단어**를 식별하여 `stop_words`에 설정:

```bash
# dry-run으로 프롬프트 확인
uv run python rag_pipeline/llm_enrich.py --dataset new_dataset --dry-run

# stop_words 설정 후 전체 enrichment
uv run python rag_pipeline/llm_enrich.py --dataset new_dataset
```

### 4단계: Bedrock 업로드 파일 준비

```bash
uv run python rag_pipeline/prepare_and_sync.py --dataset new_dataset --mode prepare
```

### 5단계: Bedrock KB 생성

```bash
uv run python rag_pipeline/create_kb.py --dataset new_dataset --mode create
```

완료 후 출력된 `s3_bucket`, `kb_id`, `ds_id` 값을 `datasets.yaml`에 반영.

### 6단계: 테스트 케이스 작성 및 평가

`evaluate_retrieval.py`에 데이터셋별 테스트 케이스 추가 후 평가:

```bash
uv run python rag_pipeline/evaluate_retrieval.py --dataset new_dataset
```
