"""프롬프트 모듈.

시스템 프롬프트와 템플릿 로더를 제공합니다.

사용법:
    from ops_agent.prompts import get_system_prompt, load_prompt

    # 설정된 언어로 시스템 프롬프트 가져오기
    prompt = get_system_prompt()

    # 특정 템플릿 로드
    custom_prompt = load_prompt("ops_agent_ko", CURRENT_TIME="2024-01-01")
"""

from ops_agent.prompts.system_prompt import (
    get_system_prompt,
    get_system_prompt_en,
    get_system_prompt_ko,
)
from ops_agent.prompts.template import PromptTemplate, PromptTemplateLoader, load_prompt

__all__ = [
    "get_system_prompt",
    "get_system_prompt_ko",
    "get_system_prompt_en",
    "load_prompt",
    "PromptTemplate",
    "PromptTemplateLoader",
]
