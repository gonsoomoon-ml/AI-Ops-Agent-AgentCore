"""Knowledge Base Mock 도구.

테스트 및 개발용 로컬 YAML 기반 KB 검색 도구를 제공합니다.
KB_MODE=mock 설정 시 사용됩니다.
"""

import json
import logging

from strands import tool

from ops_agent.tools.knowledge_base.data_loader import search_entries
from ops_agent.tools.util import Colors, log_tool_io

logger = logging.getLogger(__name__)


@tool
@log_tool_io
def kb_retrieve(
    query: str,
    category: str,
    num_results: int = 5,
) -> str:
    """Knowledge Base에서 질문에 대한 답변을 검색합니다 (Mock 모드).

    로컬 YAML 데이터에서 키워드 매칭으로 관련 문서를 찾습니다.

    Args:
        query: 검색할 질문 (예: '에러 코드 22E 해결 방법')
        category: 카테고리 필터 (필수). 예: 'diagnostics', 'firmware_update', 'glossary'
        num_results: 반환할 최대 결과 수 (기본값: 5)

    Returns:
        검색 결과 JSON 문자열.
    """
    logger.debug(f"{Colors.YELLOW}[Mock] kb_retrieve 모의 데이터 사용{Colors.END}")

    entries = search_entries(query, category=category or None, max_results=num_results)

    results = []
    for entry in entries:
        results.append({
            "doc_id": entry.get("id", "unknown"),
            "score": 1.0,
            "category": entry.get("category", ""),
            "content": entry.get("answer", "")[:500],
        })

    return json.dumps({
        "status": "success",
        "mode": "mock",
        "query": query,
        "result_count": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2)


def get_mock_tools() -> list:
    """Mock 모드에서 사용할 KB 도구 목록 반환."""
    return [kb_retrieve]
