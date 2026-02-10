"""CloudWatch MCP 도구 테스트.

MCP 모드 도구 로딩 및 기본 동작을 테스트합니다.

실행 방법:
    # Mock 모드 테스트 (기본)
    uv run pytest tests/test_cloudwatch_mcp.py -v

    # MCP 모드 테스트 (실제 MCP 서버 필요)
    CLOUDWATCH_MODE=mcp uv run pytest tests/test_cloudwatch_mcp.py -v -k mcp
"""

import json
import os
import pytest


class TestMockMode:
    """Mock 모드 테스트."""

    def test_get_mock_tools(self):
        """Mock 도구 목록 반환 테스트."""
        from ops_agent.tools.cloudwatch.mock_tools import get_mock_tools

        tools = get_mock_tools()

        assert len(tools) == 2
        tool_names = [t.__name__ for t in tools]
        assert "cloudwatch_describe_log_groups" in tool_names
        assert "cloudwatch_filter_log_events" in tool_names

    def test_mock_describe_log_groups(self):
        """Mock describe_log_groups 도구 테스트."""
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_describe_log_groups

        result = cloudwatch_describe_log_groups(prefix="")
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["mode"] == "mock"
        assert data["log_group_count"] > 0
        assert len(data["log_groups"]) > 0

    def test_mock_describe_log_groups_with_prefix(self):
        """Mock describe_log_groups prefix 필터 테스트."""
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_describe_log_groups

        result = cloudwatch_describe_log_groups(prefix="payment")
        data = json.loads(result)

        assert data["status"] == "success"
        assert all("payment" in g["logGroupName"].lower() for g in data["log_groups"])

    def test_mock_filter_log_events(self):
        """Mock filter_log_events 도구 테스트."""
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_filter_log_events

        result = cloudwatch_filter_log_events(
            log_group_name="/aws/lambda/payment-service",
            filter_pattern="?ERROR ?500",
            time_range="1h",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["mode"] == "mock"
        assert data["event_count"] == 4
        assert len(data["events"]) == 4

    def test_mock_filter_log_events_default(self):
        """Mock filter_log_events 기본 로그 테스트."""
        from ops_agent.tools.cloudwatch.mock_tools import cloudwatch_filter_log_events

        result = cloudwatch_filter_log_events(
            log_group_name="/aws/lambda/other-service",
            filter_pattern="INFO",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["event_count"] == 1


class TestToolFactory:
    """도구 팩토리 테스트."""

    def test_get_cloudwatch_tools_mock_mode(self, monkeypatch):
        """Mock 모드에서 도구 팩토리 테스트."""
        monkeypatch.setenv("CLOUDWATCH_MODE", "mock")

        # Settings 캐시 초기화
        from ops_agent.config.settings import get_settings
        get_settings.cache_clear()

        from ops_agent.tools.cloudwatch import get_cloudwatch_tools
        tools = get_cloudwatch_tools()

        assert len(tools) == 2
        tool_names = [t.__name__ for t in tools]
        assert "cloudwatch_describe_log_groups" in tool_names
        assert "cloudwatch_filter_log_events" in tool_names

        # 캐시 초기화 (다른 테스트에 영향 방지)
        get_settings.cache_clear()

    def test_get_cloudwatch_tools_invalid_mode(self, monkeypatch):
        """잘못된 모드에서 에러 발생 테스트."""
        monkeypatch.setenv("CLOUDWATCH_MODE", "invalid")

        from ops_agent.config.settings import get_settings
        get_settings.cache_clear()

        # Pydantic validation error expected
        with pytest.raises(Exception):
            from ops_agent.tools.cloudwatch import get_cloudwatch_tools
            get_cloudwatch_tools()

        get_settings.cache_clear()


class TestMCPMode:
    """MCP 모드 테스트.

    실제 MCP 서버가 필요합니다.
    CLOUDWATCH_MODE=mcp 환경변수 설정 후 실행하세요.
    """

    @pytest.mark.skipif(
        os.environ.get("CLOUDWATCH_MODE") != "mcp",
        reason="MCP 모드 테스트는 CLOUDWATCH_MODE=mcp 설정 필요"
    )
    def test_get_mcp_tools(self):
        """MCP 도구 목록 반환 테스트."""
        from ops_agent.tools.cloudwatch.mcp_tools import get_mcp_tools

        tools = get_mcp_tools()

        assert len(tools) == 1
        # MCPClient 타입 확인
        assert "MCPClient" in type(tools[0]).__name__

    @pytest.mark.skipif(
        os.environ.get("CLOUDWATCH_MODE") != "mcp",
        reason="MCP 모드 테스트는 CLOUDWATCH_MODE=mcp 설정 필요"
    )
    def test_mcp_client_creation(self):
        """MCP 클라이언트 생성 테스트."""
        from ops_agent.tools.cloudwatch.mcp_tools import get_cloudwatch_mcp_client

        client = get_cloudwatch_mcp_client()

        assert client is not None
        assert "MCPClient" in type(client).__name__


class TestSettingsIntegration:
    """Settings 통합 테스트."""

    def test_cloudwatch_mode_default(self):
        """기본 CLOUDWATCH_MODE 설정 테스트."""
        from ops_agent.config.settings import get_settings
        get_settings.cache_clear()

        # 환경 변수 없이 기본값 확인
        import os
        original = os.environ.pop("CLOUDWATCH_MODE", None)

        try:
            settings = get_settings()
            assert settings.cloudwatch_mode == "mock"
            assert settings.is_cloudwatch_mock is True
        finally:
            if original:
                os.environ["CLOUDWATCH_MODE"] = original
            get_settings.cache_clear()

    def test_is_cloudwatch_mock_property(self, monkeypatch):
        """is_cloudwatch_mock 프로퍼티 테스트."""
        from ops_agent.config.settings import get_settings

        # Mock 모드
        monkeypatch.setenv("CLOUDWATCH_MODE", "mock")
        get_settings.cache_clear()
        assert get_settings().is_cloudwatch_mock is True

        # MCP 모드
        monkeypatch.setenv("CLOUDWATCH_MODE", "mcp")
        get_settings.cache_clear()
        assert get_settings().is_cloudwatch_mock is False

        get_settings.cache_clear()
