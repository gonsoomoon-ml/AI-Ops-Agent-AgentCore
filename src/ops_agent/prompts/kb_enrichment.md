---
name: kb_enrichment
version: "3.0"
language: ko
description: Knowledge Base 엔트리 LLM enrichment 프롬프트 (HYBRID search 최적화)
---

## Context
<context>
이 Q&A 항목은 HYBRID 검색(벡터 유사도 + BM25 키워드 매칭) 데이터베이스에 저장됩니다.
BM25는 핵심 용어의 **반복 출현 빈도**로 문서를 랭킹하므로, question_variants에서 핵심 용어가 최대한 많이 반복되어야 합니다.
총 {{ total_docs }}개 문서 중에서 이 항목만 정확히 찾을 수 있도록, 구별력 있는 정보를 추출하세요.
</context>

## Input
<input>
- 제목: {{ title }}
- 카테고리: {{ category }} (같은 카테고리에 다른 항목도 있음)
- 답변: {{ answer }}
- 기존 키워드: {{ keywords }}
- 에러 코드: {{ error_codes }}
- 같은 카테고리의 다른 항목들: {{ siblings }}
</input>

## Output Format
<output_format>
아래 JSON 형식으로 **정확히** 반환하세요. 다른 텍스트 없이 JSON만 출력하세요.

```json
{
  "ko_core_term": "핵심 한국어 용어 (1-2단어, 조사 제거)",
  "en_core_term": "영어 용어가 있으면 추출, 없으면 빈 문자열",
  "ko_nouns": ["이 항목에서만 중요한 기술 명사 5-8개 (다른 문서와 겹치지 않는 용어)"],
  "question_variants": ["아래 템플릿을 사용하여 정확히 8개 생성"],
  "search_keywords": ["기존 키워드 전부 + 이 항목 고유 전문 용어 2-3개 추가 = 총 8-12개"]
}
```
</output_format>

## Instructions
<instructions>
### 1단계: 핵심 용어 추출
제목에서 ko_core_term과 en_core_term을 추출하세요.
- 제목이 "X(Y)가 무엇인가요?" 형태면: ko_core_term=X, en_core_term=Y
- 제목이 "X 방법" / "X 설명" 등 행위형이면: ko_core_term=핵심 주제 (예: "펌웨어 업데이트 실패 대처" → "펌웨어 업데이트 실패")
- 제목에 영어가 없으면: en_core_term은 답변에서 대응하는 영어 용어를 찾거나 빈 문자열
- 조사(가, 이, 를, 의, 에서, 은, 는)는 반드시 제거

### 2단계: question_variants (BM25 최적화 — 가장 중요)
**정확히 8개**를 아래 템플릿 순서대로 생성하세요. KO는 ko_core_term, EN은 en_core_term입니다.

1. `KO 알려줘`
2. `KO에 대해 설명해줘`
3. `KO가 뭐야?`
4. `KO 뭐야?`
5. EN이 있으면 → `EN이 뭐야?` / 없으면 → `KO 어떻게 해?`
6. EN이 있으면 → `EN 설명해줘` / 없으면 → `KO 알려주세요`
7. EN이 있으면 → `KO(EN) 설명해줘` / 없으면 → `KO이 뭔가요?`
8. EN이 있으면 → `KO(EN)가 무엇인가요` / 없으면 → `KO 무엇인가요?`

규칙:
- 각 변형은 **짧게** (2-5단어). 부가 설명이나 맥락 단어를 넣지 마세요.
- KO가 모든 8개에 반드시 포함되어야 합니다 (BM25 빈도 극대화).
- 위 템플릿 외의 창의적 변형은 하지 마세요.

### 3단계: ko_nouns (구별성 원칙)
답변에서 이 항목**만의** 전문 용어를 5-8개 추출하세요.

금지어 — 아래 단어는 대부분의 문서에 공통이므로 구별력이 없습니다. 절대 포함하지 마세요:
{{ stop_words }}

"같은 카테고리의 다른 항목들"에 등장하는 용어도 피하세요.

### 4단계: search_keywords
기존 키워드({{ keywords }})를 **전부** 유지하고, 답변에서 이 항목만의 고유 기술 용어 2-3개만 추가하세요.
</instructions>
