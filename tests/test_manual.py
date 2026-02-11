#!/usr/bin/env python
"""OpsAgent 수동 테스트 스크립트.

사용법:
    uv run python tests/test_manual.py
    uv run python tests/test_manual.py --test 1
    uv run python tests/test_manual.py --test 2
"""

import argparse
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


def print_header(title: str) -> None:
    """테스트 헤더 출력."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60 + "\n")


def test_1_kb_retrieve() -> None:
    """테스트 1: Knowledge Base 검색 테스트.

    Bedrock KB (Refrigerator)에 HYBRID 검색으로 기술 문서를 조회합니다.
    KB_MODE=mcp 설정 시 실제 Bedrock API를 호출합니다.

    흐름:
        [1] OpsAgent를 통한 KB 질의 (에이전트가 kb_retrieve 도구 자동 선택)
        [2] KB 도구 직접 호출로 검색된 문서 표시
    """
    import json

    from ops_agent.agent import OpsAgent
    from ops_agent.tools.knowledge_base import get_kb_tools

    print_header("테스트 1: Knowledge Base 검색 (Refrigerator KB)")

    # [1] OpsAgent를 통한 KB 질의
    print("-" * 60)
    print("[1] OpsAgent를 통한 KB 질의 (평가 없음)")
    print("-" * 60)

    agent = OpsAgent(enable_evaluation=False)
    query = "냉매가 뭐야?"
    print(f"  Q: {query}")
    print()
    agent.invoke(query)

    # [2] 검색된 문서 표시
    print()
    print("-" * 60)
    print("[2] 검색된 KB 문서 (Retrieved Documents)")
    print("-" * 60)

    kb_tools = get_kb_tools()
    kb_fn = kb_tools[0]
    result = json.loads(kb_fn(query=query, category="glossary"))

    if result["status"] == "success":
        print(f"  KB ID: {result['kb_id']}")
        print(f"  결과: {result['result_count']}건")
        print()
        for i, doc in enumerate(result["results"], 1):
            print(f"  [{i}] {doc['doc_id']} (score: {doc['score']:.4f}) [{doc['category']}]")
            print(doc["content"])
            print()
    else:
        print(f"  ERROR: {result.get('message', 'unknown')}")

    print("-" * 60)


def test_2_kb_with_evaluation() -> None:
    """테스트 2: KB 검색 + Graph 평가 워크플로우.

    KB 질의에 대해 전체 Graph 워크플로우를 실행합니다.
    ANALYZE → EVALUATE (CloudWatchChecker + KBChecker) → DECIDE → FINALIZE

    KBChecker가 KB 검색 결과의 핵심 내용이 응답에 반영되었는지 평가합니다.
    """
    from ops_agent.agent import OpsAgent

    print_header("테스트 2: KB 검색 + Graph 평가 워크플로우")
    print("ANALYZE → EVALUATE (KBChecker) → DECIDE → FINALIZE")
    print()

    agent = OpsAgent(
        enable_evaluation=True,
        max_attempts=2,
        verbose=True,
    )

    query = "냉매가 뭐야?"
    print(f"  Q: {query}")
    print()
    agent.invoke(query)
    print("-" * 60)


def main() -> None:
    """메인 함수."""
    parser = argparse.ArgumentParser(description="OpsAgent 수동 테스트")
    parser.add_argument(
        "--test", "-t",
        type=int,
        choices=[1, 2],
        help="실행할 테스트 번호 (1-2)",
    )
    args = parser.parse_args()

    tests = {
        1: ("Knowledge Base 검색 테스트", test_1_kb_retrieve),
        2: ("KB + Graph 평가 워크플로우", test_2_kb_with_evaluation),
    }

    if args.test:
        # 특정 테스트만 실행
        name, func = tests[args.test]
        func()
    else:
        # 테스트 메뉴 표시
        print("\n" + "=" * 60)
        print(" OpsAgent 수동 테스트")
        print("=" * 60)
        print("\n사용 가능한 테스트:")
        for num, (name, _) in tests.items():
            print(f"  {num}. {name}")
        print("\n실행 방법:")
        print("  uv run python tests/test_manual.py --test 1")
        print("  uv run python tests/test_manual.py -t 2")
        print()


if __name__ == "__main__":
    main()
