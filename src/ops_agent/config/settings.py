"""Pydantic 기반 애플리케이션 설정.

이 모듈은 환경 변수와 .env 파일에서 설정을 로드합니다.
Singleton 패턴으로 구현되어 애플리케이션 전체에서 동일한 설정 인스턴스를 사용합니다.

사용법:
    from ops_agent.config import get_settings
    settings = get_settings()

    if settings.is_cloudwatch_mock:
        # Mock 데이터 사용
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수에서 로드되는 애플리케이션 설정.

    .env 파일 또는 환경 변수에서 설정값을 자동으로 읽어옵니다.
    각 필드의 alias가 환경 변수 이름입니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",           # .env 파일에서 설정 로드
        env_file_encoding="utf-8", # UTF-8 인코딩 사용
        case_sensitive=False,      # 환경 변수 대소문자 구분 안함
        extra="ignore",            # 정의되지 않은 변수 무시
    )

    # ========== AWS 설정 ==========
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_profile: str | None = Field(default=None, alias="AWS_PROFILE")

    # ========== Bedrock 설정 ==========
    # 사용 가능한 모델:
    #   - global.anthropic.claude-sonnet-4-5-20250929-v1:0 (기본값, 빠름)
    #   - global.anthropic.claude-opus-4-5-20251101-v1:0 (고성능)
    bedrock_model_id: str = Field(
        default="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        alias="BEDROCK_MODEL_ID",
    )
    bedrock_temperature: float = Field(
        default=0.0,
        alias="BEDROCK_TEMPERATURE",
        ge=0.0,  # 최소값 0.0
        le=1.0,  # 최대값 1.0
    )
    bedrock_max_tokens: int = Field(
        default=4096,
        alias="BEDROCK_MAX_TOKENS",
        ge=1,     # 최소값 1
        le=8192,  # 최대값 8192
    )
    bedrock_knowledge_base_id: str | None = Field(
        default=None,
        alias="BEDROCK_KNOWLEDGE_BASE_ID",
    )

    # ========== Datadog 설정 ==========
    datadog_api_key: str | None = Field(default=None, alias="DATADOG_API_KEY")
    datadog_app_key: str | None = Field(default=None, alias="DATADOG_APP_KEY")
    datadog_site: str = Field(default="datadoghq.com", alias="DATADOG_SITE")

    # ========== Agent 설정 ==========
    agent_language: Literal["ko", "en"] = Field(default="ko", alias="AGENT_LANGUAGE")
    agent_log_level: str = Field(default="INFO", alias="AGENT_LOG_LEVEL")

    # ========== 개별 도구 Mock 모드 설정 ==========
    # 각 도구별로 Mock/Live 모드를 독립적으로 설정 가능
    cloudwatch_mock_mode: bool = Field(default=True, alias="CLOUDWATCH_MOCK_MODE")
    datadog_mock_mode: bool = Field(default=True, alias="DATADOG_MOCK_MODE")
    kb_mock_mode: bool = Field(default=True, alias="KB_MOCK_MODE")

    # ========== AgentCore Memory 설정 ==========
    agentcore_memory_enabled: bool = Field(default=False, alias="AGENTCORE_MEMORY_ENABLED")
    agentcore_memory_id: str | None = Field(default=None, alias="AGENTCORE_MEMORY_ID")
    agentcore_session_ttl: int = Field(default=3600, alias="AGENTCORE_SESSION_TTL")

    # ========== OpenTelemetry 설정 ==========
    # strands-agents[otel] 패키지의 트레이싱/모니터링 설정
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_service_name: str = Field(default="ops-ai-agent", alias="OTEL_SERVICE_NAME")
    otel_exporter_endpoint: str | None = Field(
        default=None,
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )

    @property
    def is_korean(self) -> bool:
        """한국어 모드 여부 확인."""
        return self.agent_language == "ko"

    @property
    def is_cloudwatch_mock(self) -> bool:
        """CloudWatch Mock 모드 여부 확인."""
        return self.cloudwatch_mock_mode

    @property
    def is_datadog_mock(self) -> bool:
        """Datadog Mock 모드 여부 확인."""
        return self.datadog_mock_mode

    @property
    def is_kb_mock(self) -> bool:
        """Knowledge Base Mock 모드 여부 확인."""
        return self.kb_mock_mode


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스 반환 (Singleton 패턴).

    첫 호출 시 Settings 객체를 생성하고 캐시에 저장합니다.
    이후 호출에서는 캐시된 동일한 인스턴스를 반환합니다.

    Returns:
        Settings: 애플리케이션 설정 인스턴스
    """
    return Settings()
