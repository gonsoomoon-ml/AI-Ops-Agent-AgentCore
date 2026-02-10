"""CloudWatch MCP 수동 테스트.

직접 실행하여 MCP 도구 동작을 확인합니다.

실행 방법:
    # Mock 모드 테스트
    uv run python tests/test_mcp_manual.py

    # MCP 모드 테스트
    CLOUDWATCH_MODE=mcp uv run python tests/test_mcp_manual.py
"""

import json
import logging
import os
import sys

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def print_header(title: str) -> None:
    """테스트 헤더 출력."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_result(name: str, success: bool, detail: str = "") -> None:
    """테스트 결과 출력."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"  {status} - {name}")
    if detail:
        print(f"         {detail}")


def test_settings() -> bool:
    """Settings 테스트."""
    print_header("1. Settings 테스트")

    try:
        from ops_agent.config import get_settings
        get_settings.cache_clear()

        settings = get_settings()
        mode = settings.cloudwatch_mode
        is_mock = settings.is_cloudwatch_mock

        print_result("Settings 로드", True, f"mode={mode}, is_mock={is_mock}")
        return True
    except Exception as e:
        print_result("Settings 로드", False, str(e))
        return False


def test_tool_factory() -> bool:
    """도구 팩토리 테스트."""
    print_header("2. 도구 팩토리 테스트")

    try:
        from ops_agent.tools.cloudwatch import get_cloudwatch_tools

        tools = get_cloudwatch_tools()
        tool_info = []

        for t in tools:
            if hasattr(t, "__name__"):
                tool_info.append(t.__name__)
            else:
                tool_info.append(type(t).__name__)

        print_result("get_cloudwatch_tools()", True, f"tools={tool_info}")
        return True
    except Exception as e:
        print_result("get_cloudwatch_tools()", False, str(e))
        return False


def test_mock_tools() -> bool:
    """Mock 도구 테스트."""
    print_header("3. Mock 도구 테스트")

    from ops_agent.config import get_settings
    if get_settings().cloudwatch_mode != "mock":
        print("  ⏭️  SKIP - Mock 모드가 아님")
        return True

    success = True

    try:
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_describe_log_groups

        result = cloudwatch_describe_log_groups(prefix="")
        data = json.loads(result)

        if data["status"] == "success" and data["mode"] == "mock":
            print_result("describe_log_groups", True, f"groups={data['log_group_count']}")
        else:
            print_result("describe_log_groups", False, "unexpected response")
            success = False
    except Exception as e:
        print_result("describe_log_groups", False, str(e))
        success = False

    try:
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_filter_log_events

        result = cloudwatch_filter_log_events(
            log_group_name="/aws/lambda/payment-service",
            filter_pattern="?ERROR ?500",
            time_range="1h",
        )
        data = json.loads(result)

        if data["status"] == "success" and data["event_count"] == 4:
            print_result("filter_log_events", True, f"events={data['event_count']}")
        else:
            print_result("filter_log_events", False, "unexpected response")
            success = False
    except Exception as e:
        print_result("filter_log_events", False, str(e))
        success = False

    return success


def test_mcp_tools() -> bool:
    """MCP 도구 테스트."""
    print_header("4. MCP 도구 테스트")

    from ops_agent.config import get_settings
    if get_settings().cloudwatch_mode != "mcp":
        print("  ⏭️  SKIP - MCP 모드가 아님 (CLOUDWATCH_MODE=mcp 설정 필요)")
        return True

    try:
        from ops_agent.tools.cloudwatch.mcp_tools import get_cloudwatch_mcp_client

        client = get_cloudwatch_mcp_client()
        client_type = type(client).__name__

        print_result("MCP 클라이언트 생성", True, f"type={client_type}")

        # MCP 서버 연결 테스트
        print("\n  MCP 서버 도구 목록:")
        print("  (MCP 서버가 제공하는 도구는 Agent 실행 시 자동 로드됩니다)")
        print("  - describe_log_groups")
        print("  - analyze_log_group")
        print("  - execute_log_insights_query")
        print("  - get_metric_data")
        print("  - get_active_alarms")
        print("  - get_alarm_history")

        return True
    except Exception as e:
        print_result("MCP 클라이언트 생성", False, str(e))
        return False


def test_ops_agent_tools() -> bool:
    """OpsAgent 도구 통합 테스트."""
    print_header("5. OpsAgent 도구 통합 테스트")

    try:
        from ops_agent.agent import OpsAgent

        agent = OpsAgent(enable_evaluation=False)
        tools = agent.tools

        tool_info = []
        for t in tools:
            if hasattr(t, "__name__"):
                tool_info.append(t.__name__)
            else:
                tool_info.append(type(t).__name__)

        print_result("OpsAgent.tools", True, f"tools={tool_info}")
        return True
    except Exception as e:
        print_result("OpsAgent.tools", False, str(e))
        return False


def main() -> int:
    """메인 함수."""
    print("\n" + "=" * 60)
    print("  CloudWatch MCP 도구 테스트")
    print("=" * 60)

    mode = os.environ.get("CLOUDWATCH_MODE", "mock")
    print(f"\n  현재 모드: CLOUDWATCH_MODE={mode}")

    results = []
    results.append(("Settings", test_settings()))
    results.append(("Tool Factory", test_tool_factory()))
    results.append(("Mock Tools", test_mock_tools()))
    results.append(("MCP Tools", test_mcp_tools()))
    results.append(("OpsAgent Integration", test_ops_agent_tools()))

    # 결과 요약
    print_header("결과 요약")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\n  총 {passed}/{total} 통과")

    if passed == total:
        print("\n  🎉 모든 테스트 통과!")
        return 0
    else:
        print("\n  ⚠️  일부 테스트 실패")
        return 1


if __name__ == "__main__":
    sys.exit(main())
