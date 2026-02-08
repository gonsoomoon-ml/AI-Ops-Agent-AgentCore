"""도구 공통 유틸리티.

이 모듈은 모든 도구에서 사용하는 공통 유틸리티를 제공합니다.

제공 기능:
    - Colors: 콘솔 출력용 컬러 코드
    - log_tool_io: 도구 입출력 로깅 데코레이터
    - parse_time_range: 시간 범위 문자열 파싱
"""

import functools
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable

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


def parse_time_range(time_range: str) -> tuple[int, int]:
    """시간 범위 문자열을 Unix 타임스탬프(밀리초)로 변환.

    Args:
        time_range: 시간 범위 문자열 (예: '1h', '30m', '24h', '7d')

    Returns:
        tuple[int, int]: (start_time_ms, end_time_ms) Unix 타임스탬프 (밀리초)

    Raises:
        ValueError: 유효하지 않은 time_range 형식
    """
    pattern = r"^(\d+)([mhdw])$"  # m=분, h=시간, d=일, w=주
    match = re.match(pattern, time_range.lower().strip())

    if not match:
        raise ValueError(
            f"유효하지 않은 time_range 형식: {time_range}. "
            "예상 형식: '1h', '30m', '24h', '7d'"
        )

    value = int(match.group(1))
    unit = match.group(2)

    unit_mapping = {
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
        "w": timedelta(weeks=value),
    }

    end_time = datetime.now()
    start_time = end_time - unit_mapping[unit]

    # Unix 타임스탬프 (밀리초)로 변환
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    return start_time_ms, end_time_ms
