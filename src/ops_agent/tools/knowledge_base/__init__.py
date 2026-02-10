"""Knowledge Base 도구 모듈.

KB_MODE 설정에 따라 적절한 도구를 제공합니다:
    - mock: 테스트용 로컬 YAML 검색 (기본값)
    - mcp: Bedrock Knowledge Base HYBRID 검색

사용법:
    from ops_agent.tools.knowledge_base import get_kb_tools

    tools = get_kb_tools()  # 설정에 따라 mock 또는 Bedrock KB 도구 반환
"""

import logging

from ops_agent.config import get_settings
from ops_agent.tools.util import Colors

logger = logging.getLogger(__name__)


def get_kb_tools() -> list:
    """설정에 따라 Knowledge Base 도구 목록 반환.

    Returns:
        list: KB 도구 목록

    Raises:
        ValueError: 알 수 없는 KB_MODE 값
    """
    settings = get_settings()
    mode = settings.kb_mode

    if mode == "mock":
        logger.info(f"{Colors.YELLOW}[KB] Mock 모드 사용{Colors.END}")
        from ops_agent.tools.knowledge_base.mock_tools import get_mock_tools
        return get_mock_tools()

    elif mode == "mcp":
        logger.info(f"{Colors.GREEN}[KB] Bedrock KB 모드 사용 (KB ID: {settings.bedrock_knowledge_base_id}){Colors.END}")
        from ops_agent.tools.knowledge_base.kb_tools import get_kb_tools as get_bedrock_tools
        return get_bedrock_tools()

    else:
        raise ValueError(f"알 수 없는 KB_MODE: {mode}")


__all__ = [
    "get_kb_tools",
]
