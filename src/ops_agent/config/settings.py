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

    # ========== 도구 모드 설정 ==========
    # mock: 테스트용 모의 데이터 사용
    # mcp: MCP 서버를 통한 실제 API 호출
    cloudwatch_mode: Literal["mock", "mcp"] = Field(default="mock", alias="CLOUDWATCH_MODE")
    datadog_mode: Literal["mock", "mcp"] = Field(default="mock", alias="DATADOG_MODE")
    kb_mode: Literal["mock", "mcp"] = Field(default="mock", alias="KB_MODE")

    # ========== AgentCore Memory 설정 ==========
    agentcore_memory_enabled: bool = Field(default=False, alias="AGENTCORE_MEMORY_ENABLED")
    agentcore_memory_id: str | None = Field(default=None, alias="AGENTCORE_MEMORY_ID")
    agentcore_session_ttl: int = Field(default=3600, alias="AGENTCORE_SESSION_TTL")

    # ========== Observability 설정 (관측성/모니터링) ==========
    # Strands (로컬 개발)와 AgentCore (프로덕션 배포) 각각 별도 설정
    #
    # [Strands 모드]
    #   - disabled: 관측성 비활성화
    #   - langfuse-public: Langfuse Cloud 사용
    #   - langfuse-selfhosted: 자체 호스팅 Langfuse 사용
    #
    # [AgentCore 모드]
    #   - disabled: 관측성 비활성화
    #   - langfuse-public: Langfuse Cloud 사용
    #   - langfuse-selfhosted: 자체 호스팅 Langfuse 사용
    #   - native: AWS 기본 관측성 (ADOT → CloudWatch/X-Ray)

    # Strands (로컬) Observability 모드
    strands_observability_mode: Literal[
        "disabled", "langfuse-public", "langfuse-selfhosted"
    ] = Field(default="disabled", alias="STRANDS_OBSERVABILITY_MODE")

    # AgentCore Observability 모드
    agentcore_observability_mode: Literal[
        "disabled", "langfuse-public", "langfuse-selfhosted", "native"
    ] = Field(default="disabled", alias="AGENTCORE_OBSERVABILITY_MODE")

    # 공통: 서비스 이름 (트레이스에 표시)
    otel_service_name: str = Field(default="ops-ai-agent", alias="OTEL_SERVICE_NAME")

    # ========== Langfuse Public Cloud 설정 ==========
    # langfuse-public 모드 사용 시 필요
    # API 키 발급: https://us.cloud.langfuse.com (US) 또는 https://cloud.langfuse.com (EU)
    langfuse_public_key: str | None = Field(
        default=None,
        alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        alias="LANGFUSE_SECRET_KEY",
    )
    langfuse_public_endpoint: str = Field(
        default="https://us.cloud.langfuse.com",
        alias="LANGFUSE_PUBLIC_ENDPOINT",
    )

    # ========== Langfuse Self-hosted 설정 ==========
    # langfuse-selfhosted 모드 사용 시 필요
    # 자체 호스팅 Langfuse 서버의 엔드포인트와 API 키
    langfuse_selfhosted_public_key: str | None = Field(
        default=None,
        alias="LANGFUSE_SELFHOSTED_PUBLIC_KEY",
    )
    langfuse_selfhosted_secret_key: str | None = Field(
        default=None,
        alias="LANGFUSE_SELFHOSTED_SECRET_KEY",
    )
    langfuse_selfhosted_endpoint: str | None = Field(
        default=None,
        alias="LANGFUSE_SELFHOSTED_ENDPOINT",
    )

    # ========== Observability Helper Properties ==========

    @property
    def langfuse_public_auth_header(self) -> str | None:
        """Langfuse Public Cloud용 Basic Auth 헤더 생성.

        Returns:
            str | None: 'Basic {base64(public_key:secret_key)}' 형식의 인증 헤더.
                        키가 설정되지 않은 경우 None 반환.
        """
        if self.langfuse_public_key and self.langfuse_secret_key:
            import base64

            credentials = f"{self.langfuse_public_key}:{self.langfuse_secret_key}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        return None

    @property
    def langfuse_selfhosted_auth_header(self) -> str | None:
        """Langfuse Self-hosted용 Basic Auth 헤더 생성.

        Returns:
            str | None: 'Basic {base64(public_key:secret_key)}' 형식의 인증 헤더.
                        키가 설정되지 않은 경우 None 반환.
        """
        if self.langfuse_selfhosted_public_key and self.langfuse_selfhosted_secret_key:
            import base64

            credentials = (
                f"{self.langfuse_selfhosted_public_key}:{self.langfuse_selfhosted_secret_key}"
            )
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        return None

    @property
    def langfuse_public_otel_endpoint(self) -> str:
        """Langfuse Public Cloud OTEL 엔드포인트 반환.

        Returns:
            str: '{base_url}/api/public/otel' 형식의 OTEL 엔드포인트.
        """
        return f"{self.langfuse_public_endpoint}/api/public/otel"

    @property
    def langfuse_selfhosted_otel_endpoint(self) -> str | None:
        """Langfuse Self-hosted OTEL 엔드포인트 반환.

        Returns:
            str | None: '{base_url}/api/public/otel' 형식의 OTEL 엔드포인트.
                        엔드포인트가 설정되지 않은 경우 None 반환.
        """
        if self.langfuse_selfhosted_endpoint:
            return f"{self.langfuse_selfhosted_endpoint}/api/public/otel"
        return None

    @property
    def is_korean(self) -> bool:
        """한국어 모드 여부 확인."""
        return self.agent_language == "ko"

    @property
    def is_cloudwatch_mock(self) -> bool:
        """CloudWatch Mock 모드 여부 확인."""
        return self.cloudwatch_mode == "mock"

    @property
    def is_datadog_mock(self) -> bool:
        """Datadog Mock 모드 여부 확인."""
        return self.datadog_mode == "mock"

    @property
    def is_kb_mock(self) -> bool:
        """Knowledge Base Mock 모드 여부 확인."""
        return self.kb_mode == "mock"


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스 반환 (Singleton 패턴).

    첫 호출 시 Settings 객체를 생성하고 캐시에 저장합니다.
    이후 호출에서는 캐시된 동일한 인스턴스를 반환합니다.

    Returns:
        Settings: 애플리케이션 설정 인스턴스
    """
    return Settings()
