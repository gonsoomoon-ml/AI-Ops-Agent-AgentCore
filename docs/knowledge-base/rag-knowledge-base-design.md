# RAG Knowledge Base Design for Samsung Refrigerator Q&A

> **Note:** 이 문서는 Phase 3 구현 **이전**에 작성된 설계 리서치 문서입니다. 코드 스니펫은 설계 제안이며 실제 구현과 다를 수 있습니다. 실제 구현 내용은 다음 문서를 참고하세요:
> - [KB Agent Integration](kb-agent-integration.md) — 실제 도구 구현 및 설정
> - [KB Evaluation](kb-evaluation.md) — KBChecker 평가 시스템
> - [Data Guide](data-guide.md) — 데이터 구조 및 파이프라인
>
> 주요 변경점: 임베딩 모델은 Cohere v3 대신 `amazon.titan-embed-text-v2:0` 채택, 도구 디렉토리는 `tools/knowledge/` 대신 `tools/knowledge_base/` 사용.

Phase 3 설계 문서: 삼성 냉장고 Q&A 지식베이스를 위한 RAG 시스템 설계 리서치 결과.

## 목차

- [1. 데이터셋 현황](#1-데이터셋-현황)
- [2. 정확도 우선 분석: KB vs 파일 기반 vs 컨텍스트 주입](#2-정확도-우선-분석-kb-vs-파일-기반-vs-컨텍스트-주입)
- [3. 청킹 전략](#3-청킹-전략)
- [4. 데이터 파일 구조](#4-데이터-파일-구조)
- [5. OpenSearch 인덱스 설계](#5-opensearch-인덱스-설계)
- [6. 임베딩 모델 선택](#6-임베딩-모델-선택)
- [7. 하이브리드 검색](#7-하이브리드-검색)
- [8. 벡터 스토어 없이 파일 기반 RAG](#8-벡터-스토어-없이-파일-기반-rag)
- [9. 의사결정 프레임워크](#9-의사결정-프레임워크)
- [10. 참고 자료](#10-참고-자료)

---

## 1. 데이터셋 현황

### 개요

`data/RAG/refrigerator/` 디렉토리에 삼성 냉장고 서비스/지원 Q&A **샘플 데이터**가 있음.

> **참고:** 현재 ~100개 엔트리는 샘플 데이터이며, 프로덕션 데이터셋은 이보다 상당히 클 것으로 예상됨. 따라서 설계는 **확장성을 고려한 Bedrock KB 기반 접근을 기본**으로 하되, 개발/테스트 단계에서는 파일 기반 접근도 지원.

| 항목 | 값 |
|------|-----|
| 샘플 데이터 | ~100개 Q&A 엔트리 |
| 프로덕션 예상 | 수백~수천개 이상 |
| 카테고리 수 | 9개 (확장 가능) |
| 언어 | 한국어 |
| 엔트리 당 길이 | 200~500 단어 (한국어 토큰 기준 ~400~1,200 tokens) |
| 파일 형식 | Markdown (카테고리별 1개 파일) |

### 카테고리 구성

| 파일 | 엔트리 수 | 내용 |
|------|----------|------|
| Diagnostics.md | 5 | 에러 코드, 자가진단, 센서 로그 |
| Distribution Portal.md | 8 | 펌웨어 배포 워크플로우, 테스트 제품 관리, 리콜 |
| Firmware Update.md | 10 | OTA 업데이트, Wi-Fi 요구사항, 자동/수동 업데이트 |
| Glossary.md | 23 | 기술 용어 (인버터, 컴프레서, 냉매, BESPOKE 등) |
| Model Matching.md | 7 | 모델번호 체계, 시리얼번호, 부품 호환성 |
| Product Line.md | 12 | 제품 유형 (양문형, 프렌치도어, 4도어, 비스포크 등) |
| Service Portal.md | 13 | 서비스 포털 운영 (권한, A/S 접수, 부품 주문, 보증) |
| Smart Feature.md | 10 | SmartThings 연동, AI 에너지관리, 식품관리 카메라 |
| SmartThings Portal.md | 19 | SmartThings 앱 (기기 등록, 알림, 원격 제어, 자동화) |

### 엔트리 구조 (현재)

```markdown
**title**: 냉장고 문제 발생 시 에러 코드 확인 방법
---
- **contents**: 냉장고에 문제가 발생하면 제어 패널 디스플레이에...
- **urls**: https://www.samsung.com/sec/support/home-appliances/
- **sheet**: Diagnostics
- **row**: 2
- **generated_at**: 2026-02-08T10:00:00
```

---

## 2. 정확도 우선 분석: KB vs 파일 기반 vs 컨텍스트 주입

**정확도가 최우선일 때**, 단순히 "벡터 검색이 더 정확하다"고 단정할 수 없음. 쿼리 유형과 데이터 규모에 따라 최적 접근이 다름.

> **프로덕션 데이터가 샘플보다 상당히 클 것이므로**, 컨텍스트 주입은 개발/테스트 단계의 편의 수단이며, 프로덕션 배포는 **Bedrock KB (하이브리드 검색 + 리랭킹)을 기본 전략**으로 함.

### 쿼리 유형별 정확도 비교

| 쿼리 유형 | 예시 | Bedrock KB (하이브리드) | 파일 기반 (Tool-Use) | 전체 컨텍스트 주입 |
|----------|------|----------------------|--------------------|--------------------|
| 시맨틱 (의미 기반) | "냉장고가 이상한 소리를 내요" | **우수** — 임베딩이 의미 유사도 포착 | 양호 — LLM 추론으로 가능하나 2회 도구 호출 필요할 수 있음 | **우수** — LLM이 전체 문서에서 직접 매칭 |
| 정확 매칭 (에러 코드) | "22E 에러 코드" | 양호 — BM25 컴포넌트가 처리하나 벡터 점수가 희석 | **우수** — 결정적 키워드/에러코드 직접 조회 | **우수** — 에러 코드가 컨텍스트에 존재 |
| 모델번호 기반 | "RF85A9121AP 부품 호환" | 보통 — BM25로도 영숫자 패턴 매칭이 약할 수 있음 | **우수** — 정확한 패턴 매칭 | **우수** — 모델번호가 컨텍스트에 존재 |
| 새로운 표현 (패러프레이즈) | 키워드에 없는 표현 사용 | **우수** — 임베딩이 일반화 능력 보유 | 보통 — LLM 쿼리 재구성 능력에 의존 | **우수** — LLM이 직접 의미 매칭 |
| 멀티홉 (복합 질문) | "에러 코드 확인 후 자가진단도 알려줘" | 보통 — top-K 반환으로 두 번째 토픽 누락 가능 | **우수** — 에이전트가 순차적 도구 호출 가능 | **우수** — 모든 관련 엔트리가 컨텍스트에 존재 |
| 크로스 카테고리 | "SmartThings에서 에러 코드 확인하고 펌웨어도 업데이트하려면" | 양호 — 단일 검색으로 여러 카테고리 커버 | 보통 — 에이전트가 올바른 카테고리 선택해야 함 | **우수** — 카테고리 경계 없이 전체 검색 |

### 정확도 순위 (데이터 규모별)

#### 소규모 (< 500개 엔트리) — 샘플/개발 단계

| 순위 | 접근 방식 | 정확도 근거 | 제약 |
|------|----------|-----------|------|
| **1** | **전체 컨텍스트 주입 (카테고리별)** | 검색 오류 제로, 100% 재현율 | 컨텍스트 윈도우 한계 (200K 토큰) |
| **2** | **Bedrock KB + 하이브리드 검색 + 리랭킹 + 보강 문서** | 시맨틱 + 키워드 + 리랭킹 삼중 보완 | 인프라 비용, 설정 복잡성 |
| **3** | **Tool-Use RAG + BM25 + 카테고리 컨텍스트 주입** | LLM 추론 + 키워드 매칭 + 카테고리 전체 로드 | 다단계 도구 호출 지연 |

#### 대규모 (500개 이상) — 프로덕션 단계

| 순위 | 접근 방식 | 정확도 근거 | 제약 |
|------|----------|-----------|------|
| **1** | **Bedrock KB + 하이브리드 검색 + 리랭킹 + 보강 문서** | 시맨틱 + 키워드 + 리랭킹 삼중 보완, 대규모에서도 일관된 성능 | 인프라 비용, 설정 복잡성 |
| **2** | **Bedrock KB + 하이브리드 검색 (리랭킹 없음)** | 시맨틱 + 키워드 이중 보완 | 리랭킹 대비 약간의 정확도 하락 |
| **3** | **Tool-Use RAG + BM25 + 메타데이터 필터** | LLM 추론 + 키워드 매칭 + 카테고리 필터 | 데이터 증가 시 검색 지연 증가 |
| **4** | Bedrock KB + 벡터 전용 검색 | 시맨틱은 우수하나 에러 코드 정확 매칭 누락 | BM25 미사용 시 정밀도 하락 |
| **5** | Tool-Use RAG + 키워드 전용 | 에러 코드/모델번호에 강하나 패러프레이즈 약함 | 새로운 표현 처리 불가 |

### 핵심 인사이트: 검색 단계 자체가 정확도 손실의 원인

RAG의 정확도 병목은 LLM의 답변 생성이 아니라 **검색 (Retrieval) 단계**임:

- 벡터 검색: 임베딩 공간에서의 근사 최근접 이웃 → 의미적으로 유사하지만 정확히 관련 없는 문서 반환 가능
- BM25: 토큰 매칭 → 동의어, 패러프레이즈 누락
- Top-K 제한: K=5로 설정 시, 관련 문서가 6번째에 있으면 누락

**검색 단계를 제거하면 이 손실이 사라짐.** 단, 이는 데이터가 컨텍스트 윈도우에 들어갈 때만 가능. 프로덕션 데이터가 수백~수천개 이상이면 컨텍스트 주입이 불가능하므로, **검색 품질 극대화 (하이브리드 검색 + 리랭킹 + 보강 문서)가 핵심 전략**이 됨.

### 개발/테스트 전략: 카테고리별 컨텍스트 주입 (소규모 데이터에서만 유효)

```
사용자 쿼리
    │
    ▼
에이전트가 카테고리 인덱스 확인 (~2K 토큰)
    │
    ├─ 카테고리 1~2개 식별
    │
    ▼
해당 카테고리의 전체 엔트리를 컨텍스트에 주입
    │
    ├─ Diagnostics (5개 엔트리, ~3K 토큰)
    ├─ SmartThings Portal (19개 엔트리, ~8K 토큰)
    │
    ▼
LLM이 전체 엔트리에서 직접 답변 생성
    │
    └─ 검색 오류 없음, 100% 재현율 (해당 카테고리 내)
```

이 접근의 유일한 실패 모드는 **에이전트가 잘못된 카테고리를 선택**하는 것. 이를 완화하는 방법:

1. **인덱스 파일에 풍부한 카테고리 설명과 키워드** 포함
2. **모호한 쿼리 시 2개 이상의 카테고리 로드** (합쳐도 ~15K 토큰 이내)
3. **Fallback으로 Bedrock KB 검색** — 카테고리 매칭에 실패하면 벡터 검색으로 보완

### 프로덕션 전략: Bedrock KB (하이브리드 검색 + 리랭킹)

프로덕션 데이터가 샘플보다 상당히 크므로, 검색 품질 극대화가 핵심:

```
사용자 쿼리
    │
    ▼
Bedrock KB Retrieve API
    │
    ├─ 하이브리드 검색 (BM25 0.3 + 벡터 0.7)
    ├─ 메타데이터 필터 (category, document_type)
    ├─ 리랭킹 (Cohere Rerank)
    │
    ▼
Top-K 결과 (K=5~10) → LLM에 전달
    │
    ├─ 보강 문서: 카테고리 컨텍스트 + 관련 항목 참조 포함
    │
    ▼
LLM이 검색 결과 기반 답변 생성
```

정확도 극대화를 위한 핵심 설정:
1. **보강 문서 (Enriched Documents)** — 합성 질문 변형, 키워드, 관련 항목 참조를 포함하여 임베딩 품질 향상
2. **메타데이터 필터링** — 에이전트가 카테고리를 식별하여 검색 범위를 축소
3. **리랭킹** — 초기 검색 결과를 재정렬하여 정밀도 향상
4. **하이브리드 검색** — 에러 코드/모델번호 (BM25) + 의미 기반 검색 (벡터) 모두 커버

### 데이터 규모별 정확도 최적 전략

| 데이터 규모 | 정확도 최적 전략 | 이유 |
|-----------|----------------|------|
| **< 100개 (샘플)** | 카테고리별 컨텍스트 주입 | 개발/테스트용. 검색 오류 제로 |
| **100~500개** | Bedrock KB (하이브리드) + 카테고리 컨텍스트 보완 | 벡터 검색 도입, 카테고리 필터로 범위 축소 |
| **500~2,000개** | Bedrock KB (하이브리드 + 리랭킹) + 보강 문서 | 리랭킹으로 검색 정밀도 보완 |
| **2,000개 이상** | Bedrock KB (하이브리드 + 리랭킹 + 보강 문서 + 메타데이터 필터) | 검색 품질에 전적으로 의존, 모든 최적화 적용 |

### 정확도 vs 비용/복잡성 트레이드오프

```
정확도  ▲
        │  ★ 컨텍스트 주입 (< 500개, 개발/테스트 전용)
        │
        │  ★ Bedrock KB 하이브리드 + 리랭킹 + 보강 문서 (프로덕션 권장)
        │
        │      ★ Bedrock KB 하이브리드 (리랭킹 없음)
        │
        │          ★ Tool-Use + BM25 + 카테고리 주입
        │
        │              ★ Bedrock KB 벡터 전용
        │
        │                  ★ Tool-Use 키워드 전용
        │
        └──────────────────────────────────────────▶ 비용/복잡성
                                                    + 확장성 ▶
```

> **결론: 프로덕션 데이터가 샘플보다 상당히 크므로, Bedrock KB (하이브리드 검색 + 리랭킹 + 보강 문서)을 프로덕션 기본 전략으로 함.** 개발/테스트 단계에서는 카테고리별 컨텍스트 주입을 mock 모드로 지원하여 빠른 반복 개발이 가능하도록 설계. `KB_MODE=mock` (파일 기반) / `KB_MODE=mcp` (Bedrock KB) 토글로 두 접근 모두 지원.

---

## 3. 청킹 전략

### 전략별 비교

| 전략 | 설명 | 이 데이터셋에 대한 판정 |
|------|------|----------------------|
| **청킹 없음 (1 엔트리 = 1 청크)** | 각 Q&A 엔트리를 그대로 하나의 청크로 사용 | **최적** — 엔트리가 이미 적절한 크기 |
| 고정 크기 (512 tokens, 20% overlap) | 토큰 수 기준으로 기계적 분할 | **부적절** — 답변 중간에서 분할되어 의미 훼손 |
| 부모-자식 (Hierarchical) | 작은 자식 청크로 검색, 큰 부모 청크로 컨텍스트 제공 | **불필요** — 엔트리가 충분히 작음 |
| 시맨틱 청킹 | 임베딩 유사도로 의미 경계 감지 후 분할 | **과도** — 엔트리 자체가 이미 의미 단위 |
| 문장 윈도우 | 개별 문장 임베딩, 검색 시 주변 문장 포함 | **부적합** — 엔트리가 길지 않음 |

### 핵심 근거

- 각 Q&A 엔트리는 하나의 질문에 대한 완전한 답변 (자기 완결적 의미 단위)
- 200~500 단어 (400~1,200 한국어 토큰)는 임베딩 모델의 최적 청크 크기 범위에 해당
- Stack Overflow 엔지니어링 블로그: "FAQ, 제품 설명 같은 작고 완전한 정보 조각은 청킹이 불필요하며, 오히려 문제를 일으킬 수 있음"

### 한국어 토큰 고려사항

- 한국어는 영어 대비 약 **2.36배** 더 많은 토큰을 사용 (표준 토크나이저 기준)
- 500단어 한국어 답변 ≈ 800~1,200 토큰
- NFC 유니코드 정규화 필수: 조합형 한글 음절 (예: "앤" = 2 토큰) vs 분리형 (예: "ㅇㅐㄴ" = 7 토큰)

### 권장: 문서 보강 (Enriched Documents)

청킹 대신, 임베딩 전 각 엔트리를 다음과 같이 보강:

```markdown
# 냉장고 문제 발생 시 에러 코드 확인 방법

## 자주 묻는 질문
- 냉장고 에러 코드는 어떻게 확인하나요?
- 냉장고 화면에 이상한 숫자가 깜빡여요
- SmartThings 앱에서 에러 알림을 받았어요

## 답변
냉장고에 문제가 발생하면 제어 패널 디스플레이에 에러 코드가 표시됩니다...

## 키워드
에러 코드, 에러코드, 제어 패널, SmartThings, 재부팅, error code

## 관련 항목
- 주요 에러 코드 목록 및 의미 (Diagnostics)
- 자가진단 모드 진입 방법 (Diagnostics)
```

보강 요소:
1. **합성 질문 변형** — 사용자가 실제로 물어볼 수 있는 다양한 표현
2. **한국어 키워드** — 하이브리드 검색 성능 향상
3. **관련 항목 참조** — 크로스 레퍼런스 지원

### Anthropic의 Contextual Retrieval 기법

각 청크에 LLM이 생성한 짧은 컨텍스트 (50~100 토큰)를 앞에 추가하는 방식. 검색 실패율을 최대 67% 감소시킴.

```
원본: "Revenue grew 3%"
보강: "This chunk is from ACME Corp's Q2 2023 SEC filing. Revenue grew 3%."
```

이 기법은 다른 엔트리에서 정의된 개념을 참조하는 답변에 특히 유용.

---

## 4. 데이터 파일 구조

### Bedrock KB 지원 형식

Bedrock Knowledge Base가 지원하는 콘텐츠 형식: `.txt`, `.md`, `.html`, `.doc/.docx`, `.csv`, `.xls/.xlsx`, `.pdf`, `.jpeg`, `.png`.

> **주의: JSON은 콘텐츠 형식으로 지원되지 않음.** 현재 Markdown 형식이 올바른 접근.

### 권장 S3 레이아웃

```
s3://samsung-refrigerator-kb/
  diagnostics/
    001-error-code-check.md
    001-error-code-check.md.metadata.json
    002-error-code-list.md
    002-error-code-list.md.metadata.json
    003-self-diagnosis.md
    003-self-diagnosis.md.metadata.json
  firmware-update/
    001-ota-explanation.md
    001-ota-explanation.md.metadata.json
    ...
  glossary/
    001-inverter.md
    001-inverter.md.metadata.json
    ...
  product-line/
    ...
  service-portal/
    ...
  smart-feature/
    ...
  smartthings-portal/
    ...
  distribution-portal/
    ...
  model-matching/
    ...
```

핵심 원칙: **1개 Q&A 엔트리 = 1개 파일** + 동반 메타데이터 JSON.

### 메타데이터 파일 형식 (.metadata.json)

파일명 규칙: `{소스파일명}.metadata.json` (같은 S3 폴더에 위치, 최대 10KB)

#### 기본 형식

```json
{
  "metadataAttributes": {
    "category": "Diagnostics",
    "document_type": "troubleshooting",
    "keywords_ko": "에러 코드,제어 패널,SmartThings,재부팅",
    "has_error_codes": true,
    "source_url": "https://www.samsung.com/sec/support/home-appliances/",
    "row_id": 2
  }
}
```

#### 고급 형식 (임베딩 포함 제어)

```json
{
  "metadataAttributes": {
    "category": {
      "value": { "type": "STRING", "stringValue": "Diagnostics" },
      "includeForEmbedding": true
    },
    "document_type": {
      "value": { "type": "STRING", "stringValue": "troubleshooting" },
      "includeForEmbedding": false
    },
    "keywords_ko": {
      "value": { "type": "STRING", "stringValue": "에러 코드,제어 패널,SmartThings" },
      "includeForEmbedding": true
    },
    "has_error_codes": {
      "value": { "type": "BOOLEAN", "booleanValue": true },
      "includeForEmbedding": false
    },
    "row_id": {
      "value": { "type": "NUMBER", "numberValue": 2 },
      "includeForEmbedding": false
    },
    "source_url": {
      "value": { "type": "STRING", "stringValue": "https://www.samsung.com/sec/support/home-appliances/" },
      "includeForEmbedding": false
    }
  }
}
```

`includeForEmbedding` 설정 기준:
- `true` — 카테고리명, 키워드 (임베딩에 의미적 컨텍스트 추가)
- `false` — row_id, URL, boolean 플래그 (필터링 전용)

### 메타데이터 스키마

| 속성 | 타입 | 예시 값 | 용도 |
|------|------|--------|------|
| `category` | STRING | Diagnostics, Firmware Update, ... | 1차 필터 |
| `document_type` | STRING | troubleshooting, procedure, glossary, product_info | 콘텐츠 유형 필터 |
| `keywords_ko` | STRING | "에러 코드,제어 패널,SmartThings" | 임베딩 보강 + 검색 |
| `has_error_codes` | BOOLEAN | true/false | 에러 관련 빠른 필터 |
| `related_features` | STRING | "SmartThings,서비스 모드" | 크로스 토픽 필터 |
| `source_url` | STRING | URL | 출처 추적 |
| `row_id` | NUMBER | 2 | 원본 추적 |
| `language` | STRING | "ko" | 다국어 확장 대비 |

### 카테고리별 document_type 매핑

| 카테고리 | document_type |
|---------|---------------|
| Diagnostics | troubleshooting, procedure |
| Firmware Update | procedure, explanation |
| Glossary | glossary, definition |
| Product Line | product_info |
| Service Portal | procedure, guide |
| Smart Feature | feature_info, procedure |
| SmartThings Portal | procedure, guide |
| Distribution Portal | procedure, guide |
| Model Matching | reference, lookup |

### 메타데이터 필터링 (쿼리 시)

Bedrock Retrieve API에서 지원하는 필터 연산자:

| 연산자 | 타입 | 설명 |
|--------|------|------|
| `equals` | string, number, boolean | 정확 일치 |
| `notEquals` | string, number, boolean | 불일치 |
| `greaterThan` / `lessThan` | number | 범위 비교 |
| `in` / `notIn` | string list | 목록 포함/미포함 |
| `startsWith` | string | 접두사 일치 |
| `stringContains` | string | 부분 문자열 포함 |
| `andAll` / `orAll` | compound | 복합 조건 |

필터 사용 예시:
```json
{
  "filter": {
    "andAll": [
      { "equals": { "key": "category", "value": "Diagnostics" } },
      { "equals": { "key": "has_error_codes", "value": true } }
    ]
  }
}
```

---

## 5. OpenSearch 인덱스 설계

### 현재 코드의 문제점

`under_development/knowledge_base.py` 라인 663~685의 현재 인덱스 설정:

```json
{
  "settings": { "index.knn": "true", "knn.algo_param.ef_search": 512 },
  "mappings": {
    "properties": {
      "vector": { "type": "knn_vector", "dimension": 1024,
                   "method": { "name": "hnsw", "engine": "faiss", "space_type": "l2" } },
      "text": { "type": "text" },
      "text-metadata": { "type": "text" }
    }
  }
}
```

문제점:
1. `space_type: "l2"` — 정규화된 텍스트 임베딩에는 `innerproduct`가 최적
2. `dynamic` 매핑 미설정 — 필드 타입이 자동 변경되어 `knn_vector`가 `float`로 변환될 위험
3. 메타데이터 필드 없음 — 필터링 불가
4. Bedrock 표준 필드명 미사용

### 권장 인덱스 스키마

```json
{
  "settings": {
    "index.knn": true,
    "number_of_shards": 1,
    "knn.algo_param.ef_search": 512,
    "number_of_replicas": 0
  },
  "mappings": {
    "dynamic": false,
    "properties": {
      "embeddings": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "engine": "faiss",
          "space_type": "innerproduct",
          "parameters": {
            "ef_construction": 256,
            "m": 16
          }
        }
      },
      "AMAZON_BEDROCK_TEXT_CHUNK": {
        "type": "text"
      },
      "AMAZON_BEDROCK_METADATA": {
        "type": "text",
        "index": false
      },
      "category": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword", "ignore_above": 256 }
        }
      },
      "title": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword", "ignore_above": 256 }
        }
      },
      "row_number": {
        "type": "integer"
      },
      "source_url": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword", "ignore_above": 512 }
        }
      }
    }
  }
}
```

### 설계 근거

| 결정 | 이유 |
|------|------|
| `space_type: "innerproduct"` | 임베딩 모델이 단위 정규화 벡터를 출력하므로, cosine과 동일 결과이면서 계산이 빠름 |
| `dynamic: false` | OpenSearch가 자동으로 필드 타입을 변경하는 것을 방지 (필수) |
| `AMAZON_BEDROCK_METADATA` index: false | Bedrock 내부 사용 전용 필드, 인덱싱 불필요 |
| `text` + `keyword` 서브필드 | **Bedrock가 필터링 시 `.keyword`를 자동 추가**하므로, keyword 서브필드 없으면 필터 실패 |
| `ef_construction: 256` | 100개 문서에는 기본값으로 충분하지만, 향후 확장 대비 |

### HNSW 파라미터 참고

| 파라미터 | 설명 | 기본값 | 권장 |
|---------|------|--------|------|
| `ef_construction` | 인덱스 빌드 품질 | 100~256 | 256 |
| `m` | 노드당 양방향 링크 수 | 16 | 16 |
| `ef_search` | 검색 시 품질 | 100 | 512 |

### 한국어 텍스트 분석

OpenSearch의 **Nori 분석기**가 한국어 형태소 분석 지원:

```json
"content_text": {
  "type": "text",
  "analyzer": "nori"
}
```

> **주의:** OpenSearch Serverless에서 Nori 플러그인 지원 여부 확인 필요. Managed cluster는 2023년 10월부터 지원. Serverless에서 미지원 시, 벡터 검색 위주로 운영하거나 managed cluster 사용 고려.

---

## 6. 임베딩 모델 선택

### 후보 비교

| 모델 | 차원 | 한국어 성능 | 최대 입력 | 비용 |
|------|------|-----------|----------|------|
| **Cohere Embed Multilingual v3** | 1,024 | 우수 (MIRACL SOTA) | 512 tokens | 중간 |
| Amazon Titan Embed v2 | 1,024/512/256 | 양호 | 8,192 tokens | 낮음 |

### 권장: Cohere Embed Multilingual v3

이유:
1. **다국어 균등 성능**으로 설계되어 한국어 임베딩 품질이 영어와 동등
2. MIRACL 벤치마크 (다국어 검색)에서 최고 성능
3. `input_type` 파라미터 지원 — 인덱싱 시 `search_document`, 검색 시 `search_query` 사용으로 품질 향상
4. 2025년 1월부터 Amazon Bedrock에서 멀티모달 지원과 함께 사용 가능

주의사항:
- 최대 입력 512 토큰 — 일부 긴 한국어 엔트리 (500단어 ≈ ~1,200 토큰)는 초과할 수 있음
- 초과 시 해당 엔트리만 선택적으로 분할하거나, Titan v2 (최대 8,192 토큰)를 대안으로 사용

### 차원 선택

| 차원 | 정확도 유지율 | 권장 |
|------|-------------|------|
| 1,024 | 100% (기준) | **권장** — 100개 문서에서 스토리지 비용 무시 가능 |
| 512 | ~99% | 수백만 벡터일 때 고려 |
| 256 | ~97% | 대규모에서만 의미 있음 |

---

## 7. 하이브리드 검색

### 왜 하이브리드 검색이 필수인가

이 데이터셋에서 하이브리드 검색이 순수 벡터 검색보다 우수한 이유:

| 쿼리 유형 | 벡터 검색 | BM25 (키워드) | 하이브리드 |
|----------|----------|-------------|----------|
| "냉장고가 시끄러워요" (의미 기반) | 우수 | 보통 | 우수 |
| "22E 에러 코드" (정확 매칭) | 보통 | 우수 | 우수 |
| "RF85A9121AP 펌웨어" (모델번호) | 약함 | 우수 | 우수 |
| "냉각이 안 돼요" (패러프레이즈) | 우수 | 보통 | 우수 |

### 점수 결합 방식

#### Reciprocal Rank Fusion (RRF)

순위 기반 결합으로 점수 정규화 문제를 회피. 가장 간단하고 견고한 기준선:

```
RRF_score(d) = Σ 1/(k + rank_i(d))    (각 검색기 i에 대해)
```

k = 60 (일반적). 가중치 튜닝이 불필요.

#### 가중 산술 평균 (Weighted Arithmetic Mean)

OpenSearch Serverless의 normalization processor 사용:

```json
{
  "phase_results_processors": [{
    "normalization-processor": {
      "normalization": { "technique": "min_max" },
      "combination": {
        "technique": "arithmetic_mean",
        "parameters": { "weights": [0.3, 0.7] }
      }
    }
  }]
}
```

### 권장 가중치

| 검색기 | 가중치 | 근거 |
|--------|--------|------|
| BM25 (키워드) | **0.3** | 에러 코드, 모델번호 등 정확 매칭 담당 |
| 벡터 (시맨틱) | **0.7** | 한국어 의미 기반 검색 담당 |

에러 코드 검색이 빈번하면 BM25 가중치를 0.4로 상향 조정.

---

## 8. 벡터 스토어 없이 파일 기반 RAG

### 벡터 검색을 건너뛸 수 있는 이유

| 요인 | 이 데이터셋 | 벡터 검색 필요성 |
|------|-----------|----------------|
| 데이터 규모 | ~100개 엔트리 | 불필요 (전체 메모리 적재 가능) |
| 데이터 구조 | 9개 명확한 카테고리 | 카테고리 기반 라우팅이 더 결정적 |
| 주요 쿼리 유형 | 에러 코드, 모델번호 (정확 매칭) | 키워드 매칭이 더 정확 |
| 업데이트 빈도 | Q&A 엔트리 수시 변경 가능 | 파일 기반 = 즉시 반영, 벡터 DB = 재임베딩 필요 |
| LLM 컨텍스트 윈도우 | ~100개 × ~200 토큰 = ~20K 토큰 | 직접 주입도 가능 |

### 비용 비교

| 접근 방식 | 초기 설정 | 운영 비용 | 유지보수 |
|----------|----------|----------|---------|
| YAML 파일 + 키워드 검색 | 거의 없음 | 없음 | YAML 파일 편집 |
| BM25 (rank_bm25) | < 1시간 | 없음 (인메모리) | 파일 변경 시 인덱스 재빌드 |
| SQLite FTS5 | < 2시간 | 없음 (파일 기반) | 파일 변경 시 DB 재빌드 |
| ChromaDB (로컬) | < 2시간 | 임베딩 모델 비용 | 변경 시 재임베딩 |
| Bedrock Knowledge Base | 수시간 (IAM, OpenSearch, S3) | OpenSearch + 임베딩 비용 | S3 동기화 + 재인덱싱 |

### 접근 방식 A: Tool-Use RAG (에이전트 도구 기반)

OpsAgent의 기존 아키텍처에 가장 적합한 방식. LLM 에이전트에게 지식 검색 도구를 제공:

```python
# src/ops_agent/tools/knowledge/tools.py

def get_knowledge_tools():
    """Factory: KB 모드에 따라 지식 검색 도구 반환."""

    @tool
    def list_qa_categories() -> str:
        """삼성 냉장고 Q&A 카테고리 목록 조회."""
        index = load_yaml("knowledge/refrigerator/index.yaml")
        return format_categories(index)

    @tool
    def search_qa(query: str, category: str = None) -> str:
        """Q&A 엔트리를 키워드/에러코드로 검색.
        Args:
            query: 검색 키워드 (한국어 또는 에러 코드)
            category: 선택적 카테고리 필터
        """
        results = search_yaml_files(query, category)
        return format_results(results[:5])

    @tool
    def lookup_error_code(code: str) -> str:
        """삼성 냉장고 에러 코드의 의미와 해결 방법 조회."""
        results = search_by_error_code(code)
        return format_results(results)

    return [list_qa_categories, search_qa, lookup_error_code]
```

장점:
- 기존 `get_cloudwatch_tools()` 팩토리 패턴과 동일한 구조
- 임베딩 모델 비용 없음, 인덱스 유지보수 없음
- YAML 파일 수정 시 즉시 반영
- LLM이 한국어를 네이티브로 이해하므로 "얼음이 안 나와요" → "제빙기" 매칭 가능

단점:
- 각 도구 호출이 추가 라운드트립 (단, 100개 엔트리에서는 무시 가능)
- 검색 품질이 LLM의 쿼리 구성 능력에 의존

#### 효율적 라우팅 패턴

```
사용자 쿼리 → 에이전트가 index.yaml 읽기 (~2K 토큰)
            → 적절한 카테고리 식별
            → 해당 카테고리 파일 로드 (10~15개 엔트리, ~2K 토큰)
            → 총 ~4K 토큰으로 검색 완료
```

### 접근 방식 B: BM25 보강

Tool-Use RAG에 BM25 점수를 추가하여 키워드 매칭 정확도 향상:

```python
from konlpy.tag import Okt
from rank_bm25 import BM25Okapi

okt = Okt()
docs = [entry["question"] + " " + entry["answer"] for entry in all_entries]
tokenized_docs = [okt.morphs(doc) for doc in docs]
bm25 = BM25Okapi(tokenized_docs)

# 검색
query = "냉장고 냉각이 안 됩니다"
tokenized_query = okt.morphs(query)
scores = bm25.get_scores(tokenized_query)
top_indices = scores.argsort()[-5:][::-1]
```

한국어 형태소 분석기 성능 비교 (BM25 기준):
- **Okt** — 가장 높은 검색 정확도 (AutoRAG 벤치마크)
- **Mecab** — 가장 빠른 처리 속도
- KoNLPy 라이브러리를 통해 모두 사용 가능

### 접근 방식 C: SQLite FTS5

Python 표준 라이브러리에 포함된 전문 검색 (추가 의존성 없음):

```python
import sqlite3

conn = sqlite3.connect("knowledge.db")
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS qa
    USING fts5(question, answer, keywords, error_codes, category)
""")

# BM25 랭킹 기반 검색
results = conn.execute("""
    SELECT *, rank FROM qa WHERE qa MATCH ? ORDER BY rank LIMIT 5
""", ("냉각",)).fetchall()
```

> 주의: FTS5는 한국어에 대해 기본 bigram 토큰화만 지원. 형태소 분석이 필요하면 사전 토큰화 후 저장 필요.

### YAML 파일 구조 (Tool-Use RAG용)

```yaml
# knowledge/refrigerator/diagnostics.yaml
- id: "diag-001"
  title: "냉장고 문제 발생 시 에러 코드 확인 방법"
  question_variants:
    - "냉장고 에러 코드는 어떻게 확인하나요?"
    - "냉장고 화면에 이상한 숫자가 깜빡여요"
    - "SmartThings 앱에서 에러 알림을 받았어요"
  keywords: ["에러 코드", "제어 패널", "디스플레이", "SmartThings", "재부팅"]
  error_codes: ["5E", "8E", "22E"]
  answer: |
    냉장고에 문제가 발생하면 제어 패널 디스플레이에 에러 코드가 표시됩니다.
    1. 제어 패널에서 직접 확인: ...
    2. SmartThings 앱에서 확인: ...
    3. 서비스 모드에서 확인: ...
  source_url: "https://www.samsung.com/sec/support/home-appliances/"
  related: ["diag-002", "diag-003"]
```

```yaml
# knowledge/refrigerator/index.yaml
categories:
  - id: diagnostics
    name: "진단 및 에러 코드"
    description: "에러 코드 확인, 자가진단 모드, 센서 로그"
    entry_count: 5
    top_keywords: ["에러 코드", "자가진단", "센서", "서비스 모드"]
  - id: firmware_update
    name: "펌웨어 업데이트"
    description: "OTA 업데이트, Wi-Fi 요구사항, 자동/수동 업데이트"
    entry_count: 10
    top_keywords: ["펌웨어", "OTA", "업데이트", "Wi-Fi"]
  # ...
```

---

## 9. 의사결정 프레임워크

### 데이터 규모별 권장 접근 (정확도 우선)

| 데이터 규모 | 프로덕션 권장 | 개발/테스트 권장 |
|-----------|-------------|----------------|
| **< 100개 (샘플)** | Bedrock KB (하이브리드) | 카테고리별 컨텍스트 주입 (mock 모드) |
| **100~500개** | Bedrock KB (하이브리드 + 리랭킹) | Tool-Use RAG + BM25 (mock 모드) |
| **500~2,000개** | Bedrock KB (하이브리드 + 리랭킹 + 보강 문서) | 동일 (mock 모드 한계) |
| **2,000개 이상** | Bedrock KB (하이브리드 + 리랭킹 + 보강 문서 + 메타데이터 필터) | 동일 |

### Phase 3 구현 권장

**1단계: Bedrock KB 기반 + mock 모드 병행 개발**

```
src/ops_agent/tools/knowledge/
  __init__.py          # get_knowledge_tools() 팩토리
  mock_tools.py        # YAML 파일 기반 (개발/테스트용, 카테고리별 컨텍스트 주입)
  mcp_tools.py         # Bedrock KB Retrieve API (프로덕션)
```

- 기존 `CLOUDWATCH_MODE` 패턴과 동일하게 `KB_MODE=mock/mcp` 토글
- **mock 모드** (개발/테스트): 카테고리 인덱스 조회 → 해당 카테고리 전체 엔트리를 컨텍스트에 주입 → 빠른 반복 개발
- **mcp 모드** (프로덕션): Bedrock KB Retrieve API 호출 → 하이브리드 검색 + 리랭킹

**핵심 도구 구성 (mock 모드 — 개발/테스트):**

```python
@tool
def get_qa_by_category(category: str) -> str:
    """지정된 카테고리의 모든 Q&A 엔트리를 반환.
    개발/테스트 전용: 전체 엔트리를 컨텍스트에 주입.
    """
    entries = load_yaml(f"knowledge/refrigerator/{category}.yaml")
    return format_all_entries(entries)  # 카테고리당 ~2-8K 토큰

@tool
def list_qa_categories() -> str:
    """카테고리 목록과 설명, 키워드 반환."""
    ...

@tool
def search_qa(query: str, category: str = None) -> str:
    """BM25 기반 Q&A 검색 (개발/테스트 시 벡터 검색 대용)."""
    ...

@tool
def lookup_error_code(code: str) -> str:
    """에러 코드 직접 조회 (카테고리 선택 불필요)."""
    ...
```

**핵심 도구 구성 (mcp 모드 — 프로덕션):**

```python
@tool
def search_knowledge_base(query: str, category: str = None,
                          document_type: str = None) -> str:
    """Bedrock KB를 통한 하이브리드 검색.
    Args:
        query: 자연어 검색 쿼리
        category: 메타데이터 필터 (선택)
        document_type: 문서 유형 필터 (선택)
    Returns:
        검색된 Q&A 엔트리 (리랭킹 적용)
    """
    filter_config = build_metadata_filter(category, document_type)
    results = bedrock_retrieve(query, filter=filter_config, top_k=10)
    return format_results(results)

@tool
def lookup_error_code(code: str) -> str:
    """에러 코드 직접 조회. BM25 가중치를 높여 정확 매칭 우선."""
    results = bedrock_retrieve(code, search_type="HYBRID",
                               filter={"has_error_codes": True})
    return format_results(results)
```

**2단계: 검색 품질 최적화**

프로덕션 데이터 규모에 맞춘 검색 품질 튜닝:
- **보강 문서 (Enriched Documents)**: 합성 질문 변형 + 키워드 + 관련 항목 참조
- **Contextual Retrieval**: 각 청크에 LLM 생성 컨텍스트 추가 (검색 실패율 67% 감소)
- **하이브리드 검색 가중치 튜닝**: 에러 코드/모델번호 쿼리 비율에 따라 BM25 가중치 조정
- **리랭킹**: Cohere Rerank로 초기 검색 결과 재정렬
- **정확도 보완**: 검색 결과의 카테고리를 확인하고, 해당 카테고리의 인접 엔트리도 함께 로드

**3단계: 평가 및 지속적 개선**

- 검색 정확도 벤치마크 구축 (질문-정답 쌍)
- A/B 테스트: 하이브리드 vs 벡터 전용, 가중치 변형
- 사용자 피드백 루프: 잘못된 답변 → 보강 문서 개선 → 재인덱싱

### Bedrock KB 설정 요약

| 설정 | 권장값 | 근거 |
|------|--------|------|
| 임베딩 모델 | Cohere Embed Multilingual v3 (1,024 dim) | 한국어 최적 성능 |
| 벡터 엔진 | Faiss + HNSW | OpenSearch Serverless 유일 옵션 |
| 거리 메트릭 | `innerproduct` | 정규화 벡터에 최적 |
| 청킹 전략 | `NONE` (사전 분할 파일) | 엔트리가 자기 완결적 |
| 검색 방식 | 하이브리드 (BM25 0.3 + 벡터 0.7) | 에러 코드 + 의미 검색 모두 필요 |
| 필터 차원 | category (9값), document_type, has_error_codes | 범위 지정 검색 |
| `dynamic` 매핑 | `false` (필수) | 필드 타입 변경 방지 |
| 메타데이터 타입 | `text` + `keyword` 서브필드 | Bedrock 필터링 호환 |

---

## 10. 참고 자료

### 청킹 전략

- [Anthropic: Contextual Retrieval (2024)](https://www.anthropic.com/news/contextual-retrieval) — 컨텍스트 추가로 검색 실패율 67% 감소
- [NVIDIA: Finding the Best Chunking Strategy (2024)](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/) — 청크 크기 벤치마크
- [Stack Overflow: Chunking in RAG Applications (2024)](https://stackoverflow.blog/2024/12/27/breaking-up-is-hard-to-do-chunking-in-rag-applications/) — FAQ 데이터는 청킹 불필요
- [arXiv 2409.04701: Late Chunking](https://arxiv.org/pdf/2409.04701) — 문서 전체 처리 후 청킹
- [Weaviate: Chunking Strategies for RAG](https://weaviate.io/blog/chunking-strategies-for-rag) — 전략별 비교
- [Firecrawl: Best Chunking Strategies 2025](https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025)

### OpenSearch 및 인덱스 설계

- [OpenSearch: Vector Search Documentation](https://docs.opensearch.org/latest/vector-search/)
- [AWS: OpenSearch Serverless Vector Search Collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html)
- [OpenSearch: Hybrid Search Best Practices](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/)
- [OpenSearch: Efficient k-NN Filtering](https://opensearch.org/blog/efficient-filters-in-knn/)
- [AWS: OpenSearch Nori Plugin for Korean](https://aws.amazon.com/ko/blogs/tech/amazon-opensearch-service-korean-nori-plugin-for-analysis/)
- [AWS: Metadata Filtering with Bedrock KB on OpenSearch](https://repost.aws/articles/ARCM4demU7THuwIQSTMHb83g/)

### Bedrock Knowledge Base

- [AWS: How Content Chunking Works](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html)
- [AWS: Include Metadata in Data Source](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-metadata.html)
- [AWS: Metadata Filtering for Retrieval Accuracy](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-knowledge-bases-now-supports-metadata-filtering-to-improve-retrieval-accuracy/)
- [AWS: Metadata Filtering for Tabular Data](https://aws.amazon.com/blogs/machine-learning/metadata-filtering-for-tabular-data-with-knowledge-bases-for-amazon-bedrock/)
- [AWS: Evaluate and Improve Bedrock KB Performance](https://aws.amazon.com/blogs/machine-learning/evaluate-and-improve-performance-of-amazon-bedrock-knowledge-bases/)
- [AWS: Advanced Parsing, Chunking, Query Reformulation](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-knowledge-bases-now-supports-advanced-parsing-chunking-and-query-reformulation-giving-greater-control-of-accuracy-in-rag-based-applications/)
- [AWS: Dynamic Metadata Filtering with LangChain](https://aws.amazon.com/blogs/machine-learning/dynamic-metadata-filtering-for-amazon-bedrock-knowledge-bases-with-langchain/)

### 임베딩 모델

- [AWS: Amazon Titan Text Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)
- [Cohere: Introducing Embed v3](https://cohere.com/blog/introducing-embed-v3)
- [AWS: Get Started with Titan Embeddings V2](https://aws.amazon.com/blogs/machine-learning/get-started-with-amazon-titan-text-embeddings-v2-a-new-state-of-the-art-embeddings-model-on-amazon-bedrock/)

### 파일 기반 RAG 대안

- [DigitalOcean: Beyond Vector Databases](https://www.digitalocean.com/community/tutorials/beyond-vector-databases-rag-without-embeddings)
- [Towards Data Science: When Not to Use Vector DB](https://towardsdatascience.com/when-not-to-use-vector-db/)
- [Milvus: Why Grep-Only Retrieval Burns Tokens](https://milvus.io/blog/why-im-against-claude-codes-grep-only-retrieval-it-just-burns-too-many-tokens.md)
- [Microsoft: RAG — Vector Search Is Not Enough](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/doing-rag-vector-search-is-not-enough/4161073)
- [PageIndex: From Claude Code to Agentic RAG](https://pageindex.ai/blog/claude-code-agentic-rag)
- [Alex Garcia: SQLite Hybrid Search (FTS5 + vec)](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)
- [AutoRAG: BM25 Tokenizer Benchmark](https://medium.com/@autorag/making-benchmark-of-different-tokenizer-in-bm25-134f2f0e72f8)
- [KoNLPy: Korean NLP in Python](https://konlpy.org/)

### 한국어 처리

- [CJK Text in AI Pipelines](https://tonybaloney.github.io/posts/cjk-chinese-japanese-korean-llm-ai-best-practices.html)
- [KoNLPy: Morphological Analysis and POS Tagging](https://konlpy.org/en/latest/morph/)
- [LanceDB: Chunking Analysis by Language](https://lancedb.com/blog/chunking-analysis-which-is-the-right-chunking-approach-for-your-language/)
