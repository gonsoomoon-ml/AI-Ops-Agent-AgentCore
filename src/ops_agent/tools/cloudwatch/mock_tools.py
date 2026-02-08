"""CloudWatch Mock 도구.

테스트 및 개발용 모의 CloudWatch 도구를 제공합니다.
CLOUDWATCH_MODE=mock 설정 시 사용됩니다.
"""

import json
import logging
from datetime import datetime, timedelta

from strands import tool

from ops_agent.tools.util import Colors, log_tool_io

logger = logging.getLogger(__name__)


def _get_mock_log_events(log_group_name: str, filter_pattern: str) -> list[dict]:
    """테스트용 모의 로그 이벤트 생성."""
    base_time = datetime.now()

    # payment-service의 500 에러 로그 모의 데이터
    if "payment" in log_group_name.lower() and "500" in filter_pattern:
        return [
            {
                "timestamp": (base_time - timedelta(minutes=15)).isoformat(),
                "message": "[ERROR] 500 Internal Server Error - Payment processing failed: Connection timeout to payment gateway",
                "logStreamName": "payment-service/prod/i-0abc123",
            },
            {
                "timestamp": (base_time - timedelta(minutes=12)).isoformat(),
                "message": "[ERROR] 500 Internal Server Error - Database connection pool exhausted",
                "logStreamName": "payment-service/prod/i-0abc123",
            },
            {
                "timestamp": (base_time - timedelta(minutes=8)).isoformat(),
                "message": "[ERROR] 500 Internal Server Error - Payment processing failed: Timeout waiting for response from payment-gateway-service",
                "logStreamName": "payment-service/prod/i-0def456",
            },
            {
                "timestamp": (base_time - timedelta(minutes=3)).isoformat(),
                "message": "[ERROR] 500 Internal Server Error - Redis cache connection failed, falling back to DB",
                "logStreamName": "payment-service/prod/i-0def456",
            },
        ]

    # 기본 모의 로그
    return [
        {
            "timestamp": (base_time - timedelta(minutes=5)).isoformat(),
            "message": f"[INFO] Sample log event matching filter: {filter_pattern}",
            "logStreamName": f"{log_group_name}/default-stream",
        }
    ]


def _get_mock_log_groups(prefix: str) -> list[dict]:
    """테스트용 모의 로그 그룹 목록 생성."""
    all_groups = [
        {"logGroupName": "/aws/lambda/payment-service", "storedBytes": 1024000},
        {"logGroupName": "/aws/lambda/order-service", "storedBytes": 512000},
        {"logGroupName": "/aws/lambda/user-service", "storedBytes": 256000},
        {"logGroupName": "/aws/ecs/api-gateway", "storedBytes": 2048000},
        {"logGroupName": "/aws/rds/mysql-prod", "storedBytes": 4096000},
    ]

    if prefix:
        return [g for g in all_groups if prefix.lower() in g["logGroupName"].lower()]
    return all_groups


@tool
@log_tool_io
def cloudwatch_describe_log_groups(
    prefix: str = "",
) -> str:
    """CloudWatch 로그 그룹 목록 조회.

    Args:
        prefix: 로그 그룹 이름 접두사 필터 (예: '/aws/lambda')

    Returns:
        로그 그룹 목록 JSON 문자열.
    """
    logger.debug(f"{Colors.YELLOW}[Mock] describe_log_groups 모의 데이터 사용{Colors.END}")

    log_groups = _get_mock_log_groups(prefix)

    return json.dumps({
        "status": "success",
        "mode": "mock",
        "prefix": prefix,
        "log_group_count": len(log_groups),
        "log_groups": log_groups,
    }, ensure_ascii=False, indent=2)


@tool
@log_tool_io
def cloudwatch_filter_log_events(
    log_group_name: str,
    filter_pattern: str = "",
    time_range: str = "1h",
) -> str:
    """CloudWatch Logs에서 로그 이벤트를 필터링하여 조회.

    Args:
        log_group_name: 조회할 로그 그룹 이름 (예: '/aws/lambda/payment-service')
        filter_pattern: 로그 이벤트 필터 패턴 (예: '?ERROR ?500')
        time_range: 조회 기간 (예: '1h', '30m', '24h'). 기본값 '1h'.

    Returns:
        타임스탬프와 메시지를 포함한 로그 이벤트 JSON 문자열.
    """
    logger.debug(f"{Colors.YELLOW}[Mock] filter_log_events 모의 데이터 사용{Colors.END}")

    events = _get_mock_log_events(log_group_name, filter_pattern)

    return json.dumps({
        "status": "success",
        "mode": "mock",
        "log_group": log_group_name,
        "filter_pattern": filter_pattern,
        "time_range": time_range,
        "event_count": len(events),
        "events": events,
    }, ensure_ascii=False, indent=2)


def get_mock_tools() -> list:
    """Mock 모드에서 사용할 도구 목록 반환."""
    return [
        cloudwatch_describe_log_groups,
        cloudwatch_filter_log_events,
    ]
