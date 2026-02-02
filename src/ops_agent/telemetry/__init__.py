"""Observability/Telemetry 모듈.

이 모듈은 OpsAgent의 관측성(Observability) 설정을 관리합니다.
Strands (로컬 개발)와 AgentCore (프로덕션 배포) 환경 각각에 대해
Langfuse 또는 AWS 네이티브 관측성을 설정할 수 있습니다.

지원하는 모드:
    [Strands - 로컬 개발]
    - disabled: 관측성 비활성화
    - langfuse-public: Langfuse Cloud 사용
    - langfuse-selfhosted: 자체 호스팅 Langfuse 사용

    [AgentCore - 프로덕션 배포]
    - disabled: 관측성 비활성화
    - langfuse-public: Langfuse Cloud 사용
    - langfuse-selfhosted: 자체 호스팅 Langfuse 사용
    - native: AWS 기본 관측성 (ADOT → CloudWatch/X-Ray)

사용법:
    # Strands 로컬 개발 시
    from ops_agent.telemetry import setup_strands_observability
    setup_strands_observability()

    # AgentCore 배포 시
    from ops_agent.telemetry import get_agentcore_observability_env_vars
    env_vars = get_agentcore_observability_env_vars()
    runtime.launch(env_vars=env_vars)
"""

from ops_agent.telemetry.setup import (
    get_agentcore_observability_env_vars,
    get_trace_attributes,
    setup_strands_observability,
)

__all__ = [
    "setup_strands_observability",
    "get_agentcore_observability_env_vars",
    "get_trace_attributes",
]
