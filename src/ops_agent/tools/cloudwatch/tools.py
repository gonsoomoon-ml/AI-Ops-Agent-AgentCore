"""CloudWatch 로그 및 메트릭 조회 도구.

이 모듈은 AWS CloudWatch에서 로그 이벤트를 조회하는 도구를 제공합니다.

제공 도구:
    - cloudwatch_filter_log_events: 로그 그룹에서 필터 패턴으로 로그 조회

Mock 모드:
    CLOUDWATCH_MOCK_MODE=true 설정 시 실제 API 호출 없이 모의 데이터를 반환합니다.
    payment-service + 500 에러 조합에 대한 샘플 데이터가 포함되어 있습니다.
"""

import functools
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from strands import tool

from ops_agent.config import get_settings

# ========== 로깅 설정 ==========
logger = logging.getLogger(__name__)


class Colors:
    """콘솔 출력용 컬러 코드."""

    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    END = "\033[0m"


def log_tool_io(func: Callable) -> Callable:
    """도구 함수의 입력/출력을 로깅하는 데코레이터.

    Args:
        func: 데코레이팅할 도구 함수

    Returns:
        로깅 기능이 추가된 래퍼 함수
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = func.__name__

        # 입력 로깅
        params = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        logger.info(f"{Colors.GREEN}[Tool 호출] {tool_name}({params}){Colors.END}")

        try:
            # 함수 실행
            result = func(*args, **kwargs)

            # 출력 로깅 (결과 미리보기)
            result_preview = result[:200] + "..." if len(result) > 200 else result
            logger.info(f"{Colors.BLUE}[Tool 완료] {tool_name} → {result_preview}{Colors.END}")

            return result

        except Exception as e:
            # 에러 로깅
            logger.error(f"{Colors.RED}[Tool 에러] {tool_name}: {e!s}{Colors.END}")
            raise

    return wrapper


# ========== Mock 데이터 생성 ==========


def _get_mock_log_events(log_group_name: str, filter_pattern: str) -> list[dict]:
    """테스트용 모의 로그 이벤트 생성.

    Args:
        log_group_name: 로그 그룹 이름
        filter_pattern: 필터 패턴

    Returns:
        모의 로그 이벤트 목록
    """
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


# ========== CloudWatch 도구 ==========


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
    settings = get_settings()

    # Mock 모드: 모의 데이터 반환
    if settings.is_cloudwatch_mock:
        logger.debug(f"{Colors.YELLOW}[Mock 모드] CloudWatch API 호출 대신 모의 데이터 사용{Colors.END}")

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

    # Live 모드: 실제 CloudWatch API 호출
    # TODO: Phase 2 - boto3를 사용한 실제 CloudWatch 연동 구현
    try:
        # import boto3
        # client = boto3.client('logs', region_name=settings.aws_region)
        # response = client.filter_log_events(
        #     logGroupName=log_group_name,
        #     filterPattern=filter_pattern,
        #     ...
        # )
        raise NotImplementedError("실제 CloudWatch 연동은 아직 구현되지 않음")

    except NotImplementedError:
        raise
    except Exception as e:
        error_msg = f"CloudWatch API 호출 실패: {e!s}"
        logger.error(f"{Colors.RED}{error_msg}{Colors.END}")
        return json.dumps({
            "status": "error",
            "error": error_msg,
            "log_group": log_group_name,
        }, ensure_ascii=False, indent=2)


# ========== 테스트용 코드 ==========

if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)

    # Mock 모드 테스트
    result = cloudwatch_filter_log_events(
        log_group_name="/aws/lambda/payment-service",
        filter_pattern="?ERROR ?500",
        time_range="1h",
    )
    print(result)
