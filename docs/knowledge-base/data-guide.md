# 데이터 가이드

RAG 파이프라인에 사용되는 Q&A 데이터의 구조와 처리 과정을 설명합니다.

## 개요

Synthesis data로 생성된 냉장고 기술 지원 Q&A 데이터입니다. 원본 Markdown에서 시작하여 파이프라인을 통해 Bedrock KB에 적재됩니다.

```
원본 Markdown (Q&A) → YAML 변환 → LLM 키워드 보강 → S3 업로드 아티팩트 → Bedrock KB
```

## 디렉토리 구조

```
data/RAG/
├── refrigerator/                   # 원본 Markdown (카테고리별 Q&A)
│   ├── Diagnostics.md              #   진단/에러코드 (5개 항목)
│   ├── Distribution Portal.md      #   배포 포털 (8개 항목)
│   ├── Firmware Update.md          #   펌웨어 업데이트 (10개 항목)
│   ├── Glossary.md                 #   용어 사전 (23개 항목)
│   ├── Model Matching.md           #   모델 매칭 (7개 항목)
│   ├── Product Line.md             #   제품 라인업 (12개 항목)
│   ├── Service Portal.md           #   서비스 포털 (13개 항목)
│   ├── Smart Feature.md            #   스마트 기능 (5개 항목)
│   └── SmartThings Portal.md       #   SmartThings 포털 (24개 항목)
│                                   #   총 107개 Q&A 항목
│
└── refrigerator_yaml/              # 파이프라인 처리 결과
    ├── diagnostics.yaml            #   YAML 변환 결과 (카테고리별)
    ├── ...
    ├── index.yaml                  #   전체 인덱스
    ├── enriched/                   #   LLM 키워드 보강 캐시 (107개 JSON)
    └── bedrock_upload/             #   S3 업로드 아티팩트 (214개 파일)
        ├── diagnostics-001.md      #     문서 본문
        └── diagnostics-001.md.metadata.json  # 메타데이터 (category 등)
```

## 원본 데이터 형식

각 카테고리 Markdown 파일은 `---` 구분자로 분리된 Q&A 항목으로 구성됩니다.

```markdown
**title**: 냉장고 문제 발생 시 에러 코드 확인 방법
---
- **contents**: 냉장고에 문제가 발생하면 제어 패널 디스플레이에 에러 코드가 ...
- **urls**: https://www.samsung.com/sec/support/home-appliances/
- **sheet**: Diagnostics
- **row**: 2
- **generated_at**: 2026-02-08T10:00:00
```

| 필드 | 설명 | 파이프라인 활용 |
|------|------|----------------|
| `title` | Q&A 제목 | 검색 쿼리 매칭에 사용 |
| `contents` | 답변 내용 | KB 문서 본문으로 적재 |
| `urls` | 참고 URL | 메타데이터로 보존 (운영용) |
| `sheet` | 원본 시트명 | `category` 메타데이터로 변환 |
| `row` | 원본 행 번호 | `doc_id` 생성에 사용 |
| `generated_at` | 생성 일시 | 파이프라인에서 제외 |

## YAML 변환 결과

`convert_md_to_yaml.py`가 Markdown을 구조화된 YAML로 변환합니다.

```yaml
category_id: diagnostics
category_name: Diagnostics
entry_count: 5
entries:
- title: 냉장고 문제 발생 시 에러 코드 확인 방법
  answer: '냉장고에 문제가 발생하면 ...'
  url: https://www.samsung.com/sec/support/home-appliances/
  error_codes:
  - 22E
  - 5E
  keywords:
  - 에러 코드
  - SmartThings
```

## LLM 키워드 보강

`llm_enrich.py`가 LLM을 사용하여 각 Q&A 항목의 핵심 키워드를 추출합니다. BM25 검색 최적화를 위해 키워드 반복 변형을 생성합니다.

- 보강 결과는 `enriched/` 디렉토리에 JSON 캐시로 저장
- 캐시가 있으면 LLM 호출을 건너뛰어 비용 절감
- Stop words (`datasets.yaml`에 정의)를 제외하여 키워드 품질 향상

## Bedrock 업로드 아티팩트

`prepare_and_sync.py`가 각 Q&A 항목을 Bedrock KB 형식으로 변환합니다. 항목당 2개 파일이 생성됩니다.

**문서 파일** (`diagnostics-001.md`):
```markdown
# 냉장고 문제 발생 시 에러 코드 확인 방법

냉장고에 문제가 발생하면 제어 패널 디스플레이에 에러 코드가 ...

에러 코드 확인 방법, 에러 코드 확인, 에러 코드 방법 ...
(LLM 보강 키워드 반복)
```

**메타데이터 파일** (`diagnostics-001.md.metadata.json`):
```json
{
  "metadataAttributes": {
    "doc_id": "diagnostics-001",
    "category": "diagnostics",
    "has_error_codes": true
  }
}
```

메타데이터의 `category` 필드는 검색 시 필터링에 사용됩니다.

## 새 데이터셋 추가

1. `data/RAG/<dataset>/` 디렉토리에 카테고리별 Markdown 파일 생성
2. `rag_pipeline/datasets.yaml`에 데이터셋 설정 추가 (경로, stop_words, category_names)
3. 파이프라인 실행: `convert → enrich → prepare → sync → evaluate`

자세한 파이프라인 실행 방법은 [RAG 파이프라인](rag-pipeline.md)을 참고하세요.
