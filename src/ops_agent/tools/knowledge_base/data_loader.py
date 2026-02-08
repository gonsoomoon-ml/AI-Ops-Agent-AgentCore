"""Knowledge Base 데이터 로더.

YAML 기반 KB 데이터를 로드하고 검색 기능을 제공합니다.

사용법:
    from ops_agent.tools.knowledge_base.data_loader import load_index, search_entries

    index = load_index()
    results = search_entries("에러 코드 22E")
"""

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# YAML 데이터 디렉토리
DATA_DIR = Path(__file__).parents[4] / "data" / "RAG" / "refrigerator_yaml"


@lru_cache(maxsize=1)
def load_index() -> dict:
    """인덱스 YAML 로드 (캐시됨).

    Returns:
        dict: 카테고리 인덱스 정보
    """
    index_path = DATA_DIR / "index.yaml"
    with open(index_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=16)
def load_category(category_id: str) -> dict:
    """카테고리 YAML 로드 (캐시됨).

    Args:
        category_id: 카테고리 ID (예: 'diagnostics', 'firmware_update')

    Returns:
        dict: 카테고리 데이터 (entries 포함)

    Raises:
        FileNotFoundError: 카테고리 파일이 없을 때
    """
    category_path = DATA_DIR / f"{category_id}.yaml"
    if not category_path.exists():
        raise FileNotFoundError(f"카테고리 파일 없음: {category_path}")

    with open(category_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _score_entry(entry: dict, query_tokens: list[str]) -> float:
    """항목의 검색 점수 계산.

    가중치:
        - title: 3x
        - keywords: 2x
        - error_codes: 5x
        - answer: 1x

    Args:
        entry: KB 항목
        query_tokens: 검색 쿼리 토큰 목록

    Returns:
        float: 관련성 점수
    """
    score = 0.0
    title = entry.get("title", "").lower()
    answer = entry.get("answer", "").lower()
    keywords = [k.lower() for k in entry.get("keywords", [])]
    error_codes = [c.lower() for c in entry.get("error_codes", [])]
    question_variants = [q.lower() for q in entry.get("question_variants", [])]

    for token in query_tokens:
        token_lower = token.lower()

        # title 매칭 (3x)
        if token_lower in title:
            score += 3.0

        # question_variants 매칭 (3x)
        for variant in question_variants:
            if token_lower in variant:
                score += 3.0
                break

        # keywords 매칭 (2x)
        for kw in keywords:
            if token_lower in kw or kw in token_lower:
                score += 2.0
                break

        # error_codes 매칭 (5x, 정확 매칭)
        if token_lower in error_codes:
            score += 5.0

        # answer 매칭 (1x)
        if token_lower in answer:
            score += 1.0

    return score


def search_entries(
    query: str,
    category: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    """KB 항목 검색.

    Args:
        query: 검색 쿼리
        category: 카테고리 필터 (None이면 전체 검색)
        max_results: 최대 결과 수

    Returns:
        list[dict]: 관련성 점수 순으로 정렬된 항목 목록
    """
    index = load_index()

    # 쿼리 토큰화 (공백 + 특수문자 기준)
    query_tokens = [t.strip() for t in query.split() if t.strip()]

    results: list[tuple[float, dict]] = []

    # 검색 대상 카테고리 결정
    if category:
        categories = [c for c in index["categories"] if c["id"] == category]
    else:
        categories = index["categories"]

    for cat in categories:
        try:
            cat_data = load_category(cat["id"])
        except FileNotFoundError:
            continue

        for entry in cat_data.get("entries", []):
            score = _score_entry(entry, query_tokens)
            if score > 0:
                results.append((score, entry))

    # 점수 순 정렬
    results.sort(key=lambda x: x[0], reverse=True)

    return [entry for _, entry in results[:max_results]]


def lookup_error_code(code: str) -> list[dict]:
    """에러 코드로 항목 검색.

    Args:
        code: 에러 코드 (예: '22E', '5E', '84C')

    Returns:
        list[dict]: 해당 에러 코드를 포함하는 항목 목록
    """
    index = load_index()
    code_upper = code.upper()
    results = []

    for cat in index["categories"]:
        try:
            cat_data = load_category(cat["id"])
        except FileNotFoundError:
            continue

        for entry in cat_data.get("entries", []):
            error_codes = entry.get("error_codes", [])
            if code_upper in error_codes:
                results.append(entry)

    return results
