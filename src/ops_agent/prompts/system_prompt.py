"""Ops AI Agent 시스템 프롬프트.

이 모듈은 설정된 언어에 따라 적절한 시스템 프롬프트를 반환합니다.
프롬프트는 .md 파일로 관리되며 템플릿 변수 치환을 지원합니다.

사용법:
    from ops_agent.prompts import get_system_prompt

    prompt = get_system_prompt()  # 설정된 언어로 프롬프트 반환
"""

from ops_agent.config import get_settings
from ops_agent.prompts.template import load_prompt


def get_system_prompt(**kwargs) -> str:
    """설정된 언어에 따른 시스템 프롬프트 반환.

    Args:
        **kwargs: 템플릿에 전달할 추가 변수

    Returns:
        렌더링된 시스템 프롬프트 문자열
    """
    settings = get_settings()

    # 언어에 따른 템플릿 선택
    template_name = "ops_agent_ko" if settings.is_korean else "ops_agent_en"

    return load_prompt(template_name, **kwargs)


def get_system_prompt_ko(**kwargs) -> str:
    """한국어 시스템 프롬프트 반환.

    Args:
        **kwargs: 템플릿에 전달할 추가 변수

    Returns:
        렌더링된 한국어 시스템 프롬프트 문자열
    """
    return load_prompt("ops_agent_ko", **kwargs)


def get_system_prompt_en(**kwargs) -> str:
    """영어 시스템 프롬프트 반환.

    Args:
        **kwargs: 템플릿에 전달할 추가 변수

    Returns:
        렌더링된 영어 시스템 프롬프트 문자열
    """
    return load_prompt("ops_agent_en", **kwargs)
