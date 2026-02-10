"""Knowledge Base Checker.

KB 도구 결과 대비 응답의 내용 반영 여부 검사.

검사 항목:
    1. KB 검색 결과의 핵심 내용이 응답에 반영되었는가?
"""

import json
import re

from ops_agent.evaluation.checkers.base import BaseChecker
from ops_agent.evaluation.models import CheckResult, ToolResult, ToolType


class KBChecker(BaseChecker):
    """Knowledge Base 응답 품질 검사기.

    KB 검색 결과의 핵심 내용이 에이전트 응답에 반영되었는지 검사합니다.
    """

    PASS_THRESHOLD = 0.7

    @property
    def name(self) -> str:
        return "kb_accuracy"

    def check(
        self,
        response: str,
        tool_results: list[ToolResult],
    ) -> CheckResult:
        # KB 결과만 필터링
        kb_results = [
            r for r in tool_results
            if r.tool_type == ToolType.KNOWLEDGE_BASE
        ]

        if not kb_results:
            return CheckResult(
                checker_name=self.name,
                score=1.0,
                passed=True,
                issues=[],
                details={"skipped": "no_kb_results"},
            )

        issues: list[str] = []
        total_phrases = 0
        found_phrases = 0
        response_lower = self._normalize_text(response)

        for result in kb_results:
            output = result.tool_output
            results_list = output.get("results", [])

            if not results_list:
                issues.append("KB 검색 결과 없음")
                continue

            # 상위 결과에서 핵심 구문 추출 및 확인
            top_result = results_list[0]
            content = top_result.get("content", "")
            phrases = self._extract_key_phrases(content)

            for phrase in phrases:
                total_phrases += 1
                if phrase.lower() in response_lower:
                    found_phrases += 1
                else:
                    issues.append(f"미반영: {phrase[:40]}")

        score = found_phrases / total_phrases if total_phrases > 0 else 0.0

        return CheckResult(
            checker_name=self.name,
            score=score,
            passed=score >= self.PASS_THRESHOLD,
            issues=issues[:5],
            details={
                "total_phrases": total_phrases,
                "found_phrases": found_phrases,
                "kb_results_count": len(kb_results),
            },
        )

    def _extract_key_phrases(self, content: str) -> list[str]:
        """KB 문서 content에서 핵심 구문 추출.

        추출 대상:
            - ## 답변 섹션의 핵심 문장
            - ## 핵심 키워드 섹션의 키워드
        """
        phrases = []

        # 핵심 키워드 섹션에서 추출
        keyword_match = re.search(r"## 핵심 키워드\s*\n(.+?)(?:\n##|\Z)", content, re.DOTALL)
        if keyword_match:
            keywords_text = keyword_match.group(1).strip()
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
            # 2글자 이상 키워드만 (조사/접속사 제외)
            phrases.extend([k for k in keywords if len(k) >= 2][:8])

        # 키워드가 부족하면 답변 섹션에서 보충
        if len(phrases) < 3:
            answer_match = re.search(r"## 답변\s*\n(.+?)(?:\n##|\Z)", content, re.DOTALL)
            if answer_match:
                answer_text = answer_match.group(1).strip()
                # 긴 단어(3글자+) 중 상위 5개
                words = re.findall(r"[가-힣a-zA-Z0-9]{3,}", answer_text)
                # 중복 제거, 기존 phrases에 없는 것만
                seen = set(p.lower() for p in phrases)
                for w in words:
                    if w.lower() not in seen:
                        phrases.append(w)
                        seen.add(w.lower())
                    if len(phrases) >= 8:
                        break

        return phrases
