"""Observability 설정 모듈.

이 모듈은 OpsAgent의 관측성(Observability)을 설정합니다.
Strands (로컬)와 AgentCore (프로덕션) 환경 각각에 대해 별도의 설정 함수를 제공합니다.

주요 함수:
    - setup_strands_observability(): Strands 로컬 환경의 관측성 설정
    - get_agentcore_observability_env_vars(): AgentCore 런타임에 전달할 환경 변수 반환
    - get_trace_attributes(): Strands Agent 초기화 시 사용할 트레이스 속성 반환
"""

import logging
import os

from ops_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


def setup_strands_observability() -> bool:
    """Strands (로컬) 환경의 관측성을 설정합니다.

    환경 변수 STRANDS_OBSERVABILITY_MODE에 따라 적절한 관측성 백엔드를 설정합니다.

    모드별 동작:
        - disabled: 관측성 비활성화, 아무 작업도 수행하지 않음
        - langfuse-public: Langfuse Cloud에 트레이스 전송
        - langfuse-selfhosted: 자체 호스팅 Langfuse에 트레이스 전송

    Returns:
        bool: 관측성 설정 성공 여부.
              disabled 모드인 경우 False 반환.

    Example:
        >>> from ops_agent.telemetry import setup_strands_observability
        >>> if setup_strands_observability():
        ...     print("Langfuse 관측성이 활성화되었습니다.")
    """
    settings = get_settings()
    mode = settings.strands_observability_mode

    if mode == "disabled":
        logger.info("[Strands] 관측성 비활성화됨")
        return False

    if mode == "langfuse-public":
        return _setup_langfuse(
            endpoint=settings.langfuse_public_otel_endpoint,
            auth_header=settings.langfuse_public_auth_header,
            mode_name="Strands + Langfuse Public",
        )

    if mode == "langfuse-selfhosted":
        return _setup_langfuse(
            endpoint=settings.langfuse_selfhosted_otel_endpoint,
            auth_header=settings.langfuse_selfhosted_auth_header,
            mode_name="Strands + Langfuse Self-hosted",
        )

    logger.warning(f"[Strands] 알 수 없는 관측성 모드: {mode}")
    return False


def get_agentcore_observability_env_vars() -> dict[str, str]:
    """AgentCore 런타임에 전달할 관측성 환경 변수를 반환합니다.

    환경 변수 AGENTCORE_OBSERVABILITY_MODE에 따라 적절한 환경 변수를 반환합니다.
    반환된 환경 변수는 AgentCore Runtime.launch()의 env_vars 파라미터로 전달해야 합니다.

    모드별 동작:
        - disabled: ADOT 비활성화 환경 변수 반환
        - langfuse-public: ADOT 비활성화 + Langfuse Cloud OTEL 환경 변수 반환
        - langfuse-selfhosted: ADOT 비활성화 + Self-hosted Langfuse OTEL 환경 변수 반환
        - native: 빈 딕셔너리 반환 (ADOT 기본 활성화)

    Returns:
        dict[str, str]: AgentCore 런타임에 전달할 환경 변수 딕셔너리.

    Example:
        >>> from ops_agent.telemetry import get_agentcore_observability_env_vars
        >>> from bedrock_agentcore_starter_toolkit import Runtime
        >>>
        >>> runtime = Runtime()
        >>> runtime.configure(...)
        >>> env_vars = get_agentcore_observability_env_vars()
        >>> runtime.launch(env_vars=env_vars)
    """
    settings = get_settings()
    mode = settings.agentcore_observability_mode

    if mode == "disabled":
        logger.info("[AgentCore] 관측성 비활성화됨")
        return {"DISABLE_ADOT_OBSERVABILITY": "true"}

    if mode == "native":
        logger.info("[AgentCore] 네이티브 관측성 (AWS ADOT) 활성화됨")
        # ADOT 환경 변수 반환 (토큰 메트릭 캡처를 위해 필요)
        # Reference: https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/06-AgentCore-observability/
        return {
            "OTEL_PYTHON_DISTRO": "aws_distro",
            "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
            "AGENT_OBSERVABILITY_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_TRACES_EXPORTER": "otlp",
        }

    if mode == "langfuse-public":
        endpoint = settings.langfuse_public_otel_endpoint
        auth_header = settings.langfuse_public_auth_header

        if not auth_header:
            logger.error("[AgentCore] Langfuse Public API 키가 설정되지 않았습니다")
            logger.error("  → LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 환경 변수를 확인하세요")
            return {}

        logger.info(f"[AgentCore] Langfuse Public 활성화됨: {endpoint}")
        return {
            "DISABLE_ADOT_OBSERVABILITY": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization={auth_header}",
        }

    if mode == "langfuse-selfhosted":
        endpoint = settings.langfuse_selfhosted_otel_endpoint
        auth_header = settings.langfuse_selfhosted_auth_header

        if not endpoint:
            logger.error("[AgentCore] Langfuse Self-hosted 엔드포인트가 설정되지 않았습니다")
            logger.error("  → LANGFUSE_SELFHOSTED_ENDPOINT 환경 변수를 확인하세요")
            return {}

        if not auth_header:
            logger.error("[AgentCore] Langfuse Self-hosted API 키가 설정되지 않았습니다")
            logger.error(
                "  → LANGFUSE_SELFHOSTED_PUBLIC_KEY, LANGFUSE_SELFHOSTED_SECRET_KEY 환경 변수를 확인하세요"
            )
            return {}

        logger.info(f"[AgentCore] Langfuse Self-hosted 활성화됨: {endpoint}")
        # 공식 AWS 샘플과 동일한 3개 env vars만 사용
        # Reference: awslabs/amazon-bedrock-agentcore-samples/.../runtime_with_strands_and_langfuse.ipynb
        return {
            "DISABLE_ADOT_OBSERVABILITY": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization={auth_header}",
        }

    logger.warning(f"[AgentCore] 알 수 없는 관측성 모드: {mode}")
    return {}


def get_trace_attributes(
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, str | list[str]]:
    """Strands Agent 초기화 시 사용할 트레이스 속성을 반환합니다.

    Langfuse에서 세션별, 사용자별로 트레이스를 그룹화하기 위한 속성을 생성합니다.
    관측성이 비활성화된 경우 빈 딕셔너리를 반환합니다.

    Args:
        session_id: 세션 ID. Langfuse에서 같은 세션의 트레이스를 그룹화합니다.
        user_id: 사용자 ID. Langfuse에서 사용자별 분석에 사용됩니다.

    Returns:
        dict: Strands Agent의 trace_attributes 파라미터로 전달할 딕셔너리.
              관측성 비활성화 시 빈 딕셔너리 반환.

    Example:
        >>> from strands import Agent
        >>> from ops_agent.telemetry import get_trace_attributes
        >>>
        >>> trace_attrs = get_trace_attributes(
        ...     session_id="session-123",
        ...     user_id="user@example.com",
        ... )
        >>> agent = Agent(
        ...     model=model,
        ...     tools=tools,
        ...     trace_attributes=trace_attrs,
        ... )
    """
    settings = get_settings()

    # 관측성 활성화 여부 확인:
    # 1. Strands 모드가 활성화된 경우 (로컬 개발)
    # 2. OTEL 환경 변수가 설정된 경우 (AgentCore 런타임)
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    is_observability_enabled = (
        settings.strands_observability_mode != "disabled" or otel_endpoint is not None
    )

    if not is_observability_enabled:
        return {}

    attrs: dict[str, str | list[str]] = {}

    # Langfuse 태그 추가 (모드 및 서비스 이름)
    # AgentCore 런타임인 경우 "agentcore" 태그 사용
    mode_tag = (
        settings.strands_observability_mode
        if settings.strands_observability_mode != "disabled"
        else "agentcore"
    )
    attrs["langfuse.tags"] = [
        mode_tag,
        settings.otel_service_name,
    ]

    # 세션 ID 추가 (세션별 트레이스 그룹화)
    if session_id:
        attrs["session.id"] = session_id

    # 사용자 ID 추가 (사용자별 분석)
    if user_id:
        attrs["user.id"] = user_id

    return attrs


def _setup_langfuse(
    endpoint: str | None,
    auth_header: str | None,
    mode_name: str,
) -> bool:
    """Langfuse를 StrandsTelemetry를 통해 설정합니다 (내부 함수).

    OTEL 환경 변수를 설정하고 StrandsTelemetry를 초기화합니다.
    strands-agents[otel] 패키지가 설치되어 있어야 합니다.

    Args:
        endpoint: Langfuse OTEL 엔드포인트 URL.
        auth_header: Basic Auth 헤더 ('Basic {base64_encoded_credentials}').
        mode_name: 로그 메시지에 표시할 모드 이름.

    Returns:
        bool: 설정 성공 여부.
    """
    # 엔드포인트 검증
    if not endpoint:
        logger.error(f"[{mode_name}] 엔드포인트가 설정되지 않았습니다")
        return False

    # 인증 헤더 검증
    if not auth_header:
        logger.error(f"[{mode_name}] API 키가 설정되지 않았습니다")
        return False

    # OTEL 환경 변수 설정 (StrandsTelemetry에서 사용)
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization={auth_header}"

    try:
        # StrandsTelemetry를 통해 OTEL exporter 설정
        from strands.telemetry import StrandsTelemetry

        StrandsTelemetry().setup_otlp_exporter()

        logger.info(f"[{mode_name}] 활성화됨: {endpoint}")
        return True

    except ImportError as e:
        logger.error(f"[{mode_name}] strands-agents[otel] 패키지가 설치되지 않았습니다: {e}")
        logger.error("  → 'pip install strands-agents[otel]' 명령으로 설치하세요")
        return False

    except Exception as e:
        logger.error(f"[{mode_name}] 설정 실패: {e}")
        return False
