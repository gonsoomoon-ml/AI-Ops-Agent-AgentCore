"""CloudWatch MCP 도구.

AWS CloudWatch MCP 서버를 통한 실제 CloudWatch 연동을 제공합니다.
CLOUDWATCH_MODE=mcp 설정 시 사용됩니다.

MCP 서버 설치:
    uvx awslabs.cloudwatch-mcp-server@latest

제공 도구 (MCP 서버):
    - describe_log_groups: 로그 그룹 목록 조회
    - analyze_log_group: 로그 분석 (이상 탐지, 패턴 분석)
    - execute_log_insights_query: Logs Insights 쿼리 실행
    - get_metric_data: 메트릭 데이터 조회
    - get_active_alarms: 활성 알람 조회
    - get_alarm_history: 알람 이력 조회

Reference:
    - https://awslabs.github.io/mcp/servers/cloudwatch-mcp-server
    - https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/mcp-tools/
"""

import logging

from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient

from ops_agent.tools.util import Colors

logger = logging.getLogger(__name__)

# MCP 서버 설정
CLOUDWATCH_MCP_SERVER = "awslabs.cloudwatch-mcp-server@latest"


def get_cloudwatch_mcp_client() -> MCPClient:
    """CloudWatch MCP 클라이언트 생성.

    Returns:
        MCPClient: CloudWatch MCP 서버에 연결된 클라이언트
    """
    logger.info(
        f"{Colors.GREEN}[MCP] CloudWatch MCP 서버 연결: {CLOUDWATCH_MCP_SERVER}{Colors.END}"
    )

    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="uvx",
                args=[CLOUDWATCH_MCP_SERVER],
            )
        )
    )


def get_mcp_tools() -> list:
    """MCP 모드에서 사용할 도구 목록 반환.

    Returns:
        list: MCPClient를 포함한 도구 목록
    """
    return [get_cloudwatch_mcp_client()]
