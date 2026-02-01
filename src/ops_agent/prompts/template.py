"""프롬프트 템플릿 로더.

Markdown 파일에서 프롬프트 템플릿을 로드하고 변수를 치환합니다.

사용법:
    from ops_agent.prompts.template import load_prompt

    prompt = load_prompt("ops_agent_ko", tools=["cloudwatch_filter_log_events"])
"""

import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


class PromptTemplate:
    """Markdown 파일에서 로드된 프롬프트 템플릿.

    지원 기능:
        - YAML frontmatter 메타데이터 파싱
        - {{ variable }} 형식의 변수 치환
        - ## 섹션별 추출
    """

    def __init__(self, content: str) -> None:
        """프롬프트 템플릿 초기화.

        Args:
            content: 템플릿 내용 (frontmatter 포함 가능)
        """
        self.raw_content = content
        self._metadata: dict[str, Any] = {}
        self._content: str = ""
        self._parse()

    def _parse(self) -> None:
        """Frontmatter와 본문 파싱."""
        # YAML frontmatter 패턴: ---\n...\n---
        frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(frontmatter_pattern, self.raw_content, re.DOTALL)

        if match:
            # 간단한 YAML 파싱 (yaml 라이브러리 의존성 제거)
            frontmatter = match.group(1)
            for line in frontmatter.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    self._metadata[key.strip()] = value.strip().strip('"').strip("'")
            self._content = self.raw_content[match.end() :]
        else:
            self._content = self.raw_content

    @property
    def metadata(self) -> dict[str, Any]:
        """템플릿 메타데이터 반환."""
        return self._metadata

    @property
    def content(self) -> str:
        """템플릿 본문 반환 (frontmatter 제외)."""
        return self._content

    def render(self, **kwargs: Any) -> str:
        """변수 치환하여 템플릿 렌더링.

        Args:
            **kwargs: 치환할 변수들

        Returns:
            렌더링된 프롬프트 문자열
        """
        result = self._content

        # 기본 변수 추가
        defaults = {
            "CURRENT_TIME": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        defaults.update(kwargs)

        # {{ variable }} 형식 치환
        for key, value in defaults.items():
            # 리스트인 경우 문자열로 변환
            if isinstance(value, list):
                value = "\n".join(f"- {item}" for item in value)
            result = re.sub(rf"\{{\{{\s*{key}\s*\}}\}}", str(value), result)

        return result

    def get_section(self, header: str) -> str | None:
        """특정 섹션 추출.

        Args:
            header: 섹션 헤더 텍스트 (# 제외)

        Returns:
            섹션 내용 또는 None
        """
        pattern = rf"^(#+)\s*{re.escape(header)}\s*\n(.*?)(?=\n#+\s|\Z)"
        match = re.search(pattern, self._content, re.MULTILINE | re.DOTALL)

        if match:
            return match.group(2).strip()
        return None


class PromptTemplateLoader:
    """프롬프트 템플릿 로더.

    사용법:
        loader = PromptTemplateLoader()
        template = loader.load("ops_agent_ko")
        prompt = template.render(tools=["tool1", "tool2"])
    """

    def __init__(self, prompts_dir: str | None = None) -> None:
        """템플릿 로더 초기화.

        Args:
            prompts_dir: 프롬프트 디렉토리 경로. 기본값은 이 파일의 디렉토리.
        """
        if prompts_dir is None:
            self.prompts_dir = Path(__file__).parent
        else:
            self.prompts_dir = Path(prompts_dir)

    @lru_cache(maxsize=16)
    def load(self, name: str) -> PromptTemplate:
        """이름으로 프롬프트 템플릿 로드.

        Args:
            name: 템플릿 이름 (.md 확장자 제외)

        Returns:
            PromptTemplate 인스턴스

        Raises:
            FileNotFoundError: 템플릿 파일을 찾을 수 없는 경우
        """
        # .md 확장자 자동 추가
        candidates = [
            self.prompts_dir / f"{name}.md",
            self.prompts_dir / name,
        ]

        for path in candidates:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                return PromptTemplate(content)

        raise FileNotFoundError(
            f"프롬프트 템플릿 '{name}'을(를) 찾을 수 없습니다. "
            f"검색 경로: {self.prompts_dir}"
        )

    def list_templates(self) -> list[str]:
        """사용 가능한 템플릿 목록 반환."""
        templates = []
        for path in self.prompts_dir.glob("*.md"):
            templates.append(path.stem)
        return sorted(templates)

    def clear_cache(self) -> None:
        """템플릿 캐시 초기화."""
        self.load.cache_clear()


# ========== 싱글톤 인스턴스 ==========
_default_loader: PromptTemplateLoader | None = None


def get_template_loader(prompts_dir: str | None = None) -> PromptTemplateLoader:
    """기본 템플릿 로더 싱글톤 반환."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptTemplateLoader(prompts_dir)
    return _default_loader


def load_prompt(name: str, **kwargs: Any) -> str:
    """프롬프트 템플릿 로드 및 렌더링 편의 함수.

    Args:
        name: 템플릿 이름
        **kwargs: 치환할 변수들

    Returns:
        렌더링된 프롬프트 문자열
    """
    loader = get_template_loader()
    template = loader.load(name)
    return template.render(**kwargs)
