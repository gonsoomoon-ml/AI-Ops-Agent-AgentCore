"""Knowledge Base Bedrock 도구.

Bedrock Knowledge Base의 HYBRID 검색 (vector + BM25)을 통한 실제 KB 도구입니다.
KB_MODE=mcp 설정 시 사용됩니다.

사용법:
    from ops_agent.tools.knowledge_base.kb_tools import get_kb_tools
"""

import json
import logging

import boto3
from strands import tool

from ops_agent.config import get_settings
from ops_agent.tools.util import Colors, log_tool_io

logger = logging.getLogger(__name__)

# Bedrock Agent Runtime client (lazy init)
_client = None


def _get_client():
    """Bedrock Agent Runtime 클라이언트 (싱글톤)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = boto3.client("bedrock-agent-runtime", region_name=settings.aws_region)
    return _client


@tool
@log_tool_io
def kb_retrieve(
    query: str,
    category: str,
    num_results: int = 5,
) -> str:
    """Knowledge Base에서 질문에 대한 답변을 검색합니다.

    Samsung Bridge (TSS/CMS/SMF/OMC/PAI) 또는 냉장고 기술 지원 문서에서
    HYBRID 검색 (벡터 + BM25)으로 관련 문서를 찾습니다.

    Args:
        query: 검색할 질문 (예: 'TSS Activation이 뭐야?', '에러 코드 22E 해결 방법')
        category: 카테고리 필터 (필수). 사용 가능한 카테고리:
            Bridge: 'tss', 'cms_portal', 'pai_portal', 'app_delivery', 'omc_update',
                    'grasse_portal', 'smf', 'client', 'glossary'
            Refrigerator: 'diagnostics', 'firmware_update', 'glossary', 'model_matching',
                         'product_line', 'service_portal', 'smart_feature', 'smartthings_portal'
        num_results: 반환할 최대 결과 수 (기본값: 5)

    Returns:
        검색 결과 JSON 문자열 (doc_id, score, content 포함).
    """
    settings = get_settings()
    kb_id = settings.bedrock_knowledge_base_id

    if not kb_id:
        return json.dumps({
            "status": "error",
            "message": "BEDROCK_KNOWLEDGE_BASE_ID가 설정되지 않았습니다. .env 파일을 확인하세요.",
        }, ensure_ascii=False)

    client = _get_client()

    # HYBRID 검색 설정
    vector_config = {
        "numberOfResults": num_results,
        "overrideSearchType": "HYBRID",
    }
    if category:
        vector_config["filter"] = {
            "equals": {"key": "category", "value": category}
        }

    try:
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": vector_config},
        )
    except Exception as e:
        logger.error(f"{Colors.RED}[KB] Bedrock Retrieve 실패: {e}{Colors.END}")
        return json.dumps({
            "status": "error",
            "message": f"KB 검색 실패: {e}",
        }, ensure_ascii=False)

    # 결과 파싱
    results = []
    for r in response.get("retrievalResults", []):
        metadata = r.get("metadata", {})
        source_uri = metadata.get("x-amz-bedrock-kb-source-uri", "")
        doc_id = source_uri.split("/")[-1].replace(".md", "") if source_uri else "unknown"

        results.append({
            "doc_id": doc_id,
            "score": r.get("score", 0),
            "category": metadata.get("category", ""),
            "content": r.get("content", {}).get("text", ""),
        })

    return json.dumps({
        "status": "success",
        "mode": "bedrock",
        "kb_id": kb_id,
        "query": query,
        "result_count": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2)


def get_kb_tools() -> list:
    """Bedrock KB 모드에서 사용할 도구 목록 반환."""
    return [kb_retrieve]
