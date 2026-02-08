"""CloudWatch 도구 모듈.

CLOUDWATCH_MODE 설정에 따라 적절한 도구를 제공합니다:
    - mock: 테스트용 모의 데이터 (기본값)
    - mcp: AWS CloudWatch MCP 서버

사용법:
    from ops_agent.tools.cloudwatch import get_cloudwatch_tools

    tools = get_cloudwatch_tools()  # 설정에 따라 mock 또는 mcp 도구 반환
"""

import logging

from ops_agent.config import get_settings
from ops_agent.tools.util import Colors

logger = logging.getLogger(__name__)


def get_cloudwatch_tools() -> list:
    """설정에 따라 CloudWatch 도구 목록 반환.

    Returns:
        list: CloudWatch 도구 목록

    Raises:
        ValueError: 알 수 없는 CLOUDWATCH_MODE 값
    """
    settings = get_settings()
    mode = settings.cloudwatch_mode

    if mode == "mock":
        logger.info(f"{Colors.YELLOW}[CloudWatch] Mock 모드 사용{Colors.END}")
        from ops_agent.tools.cloudwatch.mock_tools import get_mock_tools
        return get_mock_tools()

    elif mode == "mcp":
        logger.info(f"{Colors.GREEN}[CloudWatch] MCP 모드 사용{Colors.END}")
        from ops_agent.tools.cloudwatch.mcp_tools import get_mcp_tools
        return get_mcp_tools()

    else:
        raise ValueError(f"알 수 없는 CLOUDWATCH_MODE: {mode}")


# 하위 호환성을 위한 개별 도구 export (Mock 모드 기본)
from ops_agent.tools.cloudwatch.mock_tools import (
    cloudwatch_describe_log_groups,
    cloudwatch_filter_log_events,
)

__all__ = [
    "get_cloudwatch_tools",
    "cloudwatch_describe_log_groups",
    "cloudwatch_filter_log_events",
]
