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


def print_result(response: str) -> None:
    """테스트 결과 출력."""
    print("-" * 60)
    print("응답:")
    print("-" * 60)
    print(response)
    print("-" * 60 + "\n")


def test_1_cloudwatch_logs() -> None:
    """테스트 1: CloudWatch 로그 조회 (Graph 기반 워크플로우).

    흐름:
        [1] 사용자 질문
        [2] Graph 워크플로우 실행
            - ANALYZE: LLM 에이전트 실행 + 도구 호출
            - EVALUATE: 응답 품질 평가
            - DECIDE: 판정 (PASS/REGENERATE/BLOCK)
            - FINALIZE: 최종 출력
    """
    from ops_agent.agent import OpsAgent

    print_header("테스트 1: CloudWatch 로그 조회")

    # [1] 사용자 질문
    prompt = "payment-service에서 500 에러 로그 보여줘"
    print("-" * 60)
    print("[1] 사용자 질문")
    print("-" * 60)
    print(f"    {prompt}")
    print()

    # [2] Graph 워크플로우 실행
    print("-" * 60)
    print("[2] Graph 워크플로우 실행")
    print("    ANALYZE → EVALUATE → DECIDE → FINALIZE")
    print("-" * 60)
    agent = OpsAgent()
    agent.invoke(prompt)
    print("-" * 60)


def test_2_message_injection() -> None:
    """테스트 2: Message Injection (Mock 도구 결과 주입).

    흐름:
        [1] Mock Tool Result (주입될 도구 결과)
        [2] Mock Messages (디버깅용 - Agent에 주입될 대화 히스토리)
        [3] Agent.invoke_with_mock_history() 실행
            - 사용자 질문 + Mock 메시지 → LLM 호출 → 응답
    """
    import json
    from ops_agent.agent import OpsAgent

    print_header("테스트 2: Message Injection")
    print("Mock 도구 결과를 주입하여 에이전트 응답 테스트")
    print()

    # Mock 도구 결과
    mock_results = [
        {
            "tool_name": "cloudwatch_filter_log_events",
            "tool_input": {
                "log_group_name": "/aws/lambda/order-service",
                "filter_pattern": "?ERROR ?timeout",
                "time_range": "30m",
            },
            "tool_result": """{
                "status": "success",
                "mode": "mock",
                "log_group": "/aws/lambda/order-service",
                "event_count": 2,
                "events": [
                    {"timestamp": "2026-01-31T02:00:00", "message": "[ERROR] Database connection timeout after 30s"},
                    {"timestamp": "2026-01-31T02:05:00", "message": "[ERROR] Redis timeout: failed to get cache"}
                ]
            }""",
        }
    ]

    agent = OpsAgent()

    # [1] Mock Tool Result 출력
    print("-" * 60)
    print("[1] Mock Tool Result (주입될 도구 결과)")
    print("-" * 60)
    print(json.dumps(json.loads(mock_results[0]["tool_result"]), indent=2, ensure_ascii=False))
    print()

    # [2] Mock Messages 출력 (디버깅용)
    print("-" * 60)
    print("[2] Mock Messages (Agent에 주입될 대화 히스토리)")
    print("-" * 60)
    mock_messages = agent._build_mock_messages(mock_results)
    print(json.dumps(mock_messages, indent=2, ensure_ascii=False))
    print()

    # [3] Agent.invoke_with_mock_history() 실행
    print("-" * 60)
    print("[3] Agent.invoke_with_mock_history() 실행")
    print("    - 사용자 질문 + Mock 메시지 → LLM 호출")
    print("-" * 60)
    prompt = "이 에러들의 원인을 분석하고 해결 방안을 알려줘"
    print(f"    질문: {prompt}")
    print()

    agent.invoke_with_mock_history(prompt, mock_results)
    print("-" * 60)


def test_3_tool_only() -> None:
    """테스트 3: CloudWatch 도구만 테스트."""
    from ops_agent.tools.cloudwatch import cloudwatch_filter_log_events

    print_header("테스트 3: CloudWatch 도구 직접 테스트")
    print("cloudwatch_filter_log_events 도구 직접 호출")
    print()

    result = cloudwatch_filter_log_events(
        log_group_name="/aws/lambda/payment-service",
        filter_pattern="?ERROR ?500",
        time_range="1h",
    )
    print_result(result)


def test_4_prompt_only() -> None:
    """테스트 4: 시스템 프롬프트 확인."""
    from ops_agent.prompts import get_system_prompt

    print_header("테스트 4: 시스템 프롬프트 확인")
    print("현재 설정된 시스템 프롬프트 (처음 500자)")
    print()

    prompt = get_system_prompt()
    print(prompt[:500] + "...")


def test_5_settings() -> None:
    """테스트 5: 설정 확인."""
    from ops_agent.config import get_settings

    print_header("테스트 5: 설정 확인")

    settings = get_settings()
    print(f"AWS Region: {settings.aws_region}")
    print(f"Bedrock Model: {settings.bedrock_model_id}")
    print(f"Temperature: {settings.bedrock_temperature}")
    print(f"Max Tokens: {settings.bedrock_max_tokens}")
    print(f"Language: {settings.agent_language}")
    print(f"CloudWatch Mock: {settings.is_cloudwatch_mock}")
    print(f"Datadog Mock: {settings.is_datadog_mock}")
    print(f"KB Mock: {settings.is_kb_mock}")
    print()


def test_6_graph_regeneration() -> None:
    """테스트 6: Graph 워크플로우 REGENERATE 테스트.

    Mock 응답을 사용하여 REGENERATE 루프 흐름 확인.

    흐름:
        [1] Mock 설정 (1차: 나쁜 응답 → 2차: 좋은 응답)
        [2] Graph 워크플로우 실행
            - ANALYZE (1차) → EVALUATE → DECIDE → REGENERATE
            - ANALYZE (2차) → EVALUATE → DECIDE → FINALIZE
        [3] 최종 결과 확인
    """
    from unittest.mock import patch, MagicMock
    from ops_agent.graph import OpsAgentGraph
    from ops_agent.evaluation.models import ToolResult, ToolType

    print_header("테스트 6: Graph 워크플로우 REGENERATE")
    print("Mock 응답으로 REGENERATE 루프 테스트")
    print()

    # Mock 도구 결과 (Ground Truth)
    mock_tool_output = {
        "status": "success",
        "log_group": "/aws/lambda/payment-service",
        "filter_pattern": "?ERROR ?500",
        "time_range": "1h",
        "event_count": 4,
        "events": [
            {"timestamp": "2026-01-31T03:00:00", "message": "[ERROR] 500 - Connection timeout to payment gateway"},
            {"timestamp": "2026-01-31T03:03:00", "message": "[ERROR] 500 - Database connection pool exhausted"},
            {"timestamp": "2026-01-31T03:07:00", "message": "[ERROR] 500 - Redis cache connection failed"},
            {"timestamp": "2026-01-31T03:12:00", "message": "[ERROR] 500 - Timeout waiting for response"},
        ],
    }

    mock_tool_result = ToolResult(
        tool_type=ToolType.CLOUDWATCH,
        tool_name="cloudwatch_filter_log_events",
        tool_input={"log_group_name": "/aws/lambda/payment-service"},
        tool_output=mock_tool_output,
    )

    # 1차 응답: 나쁜 응답 (REGENERATE 유도)
    bad_response = """## 조회 결과

payment-service에서 **10건의 에러**가 발생했습니다.

### 분석
일반적인 서버 오류가 발생하고 있습니다.

### 권장 조치
시스템을 점검하세요.
"""

    # 2차 응답: 좋은 응답 (PASS 유도)
    good_response = """## 조회 결과

최근 1시간 동안 payment-service에서 **4건의 에러**가 발생했습니다.

### 에러 상세

1. **03:00:00** - Connection timeout to payment gateway
2. **03:03:00** - Database connection pool exhausted
3. **03:07:00** - Redis cache connection failed
4. **03:12:00** - Timeout waiting for response

### 분석

주요 문제점:
- **Payment Gateway 연결 문제**: 외부 결제 게이트웨이 타임아웃
- **데이터베이스 리소스 부족**: 커넥션 풀 고갈
- **캐시 서버 장애**: Redis 연결 실패

### 권장 조치

1. Payment gateway 서비스 상태 확인
2. 데이터베이스 커넥션 풀 설정 검토
3. Redis 클러스터 상태 점검
"""

    # [1] Mock 설정 설명
    print("-" * 60)
    print("[1] Mock 설정")
    print("-" * 60)
    print("  1차 응답 (나쁜 응답):")
    print("    ❌ 이벤트 수: 10건 (실제: 4건)")
    print("    ❌ 에러 내용 미인용")
    print("    ❌ 구체적 분석 없음")
    print()
    print("  2차 응답 (좋은 응답):")
    print("    ✅ 정확한 이벤트 수 (4건)")
    print("    ✅ 에러 내용 정확히 인용")
    print("    ✅ 구체적인 분석 및 권장 조치")
    print()

    # [2] Graph 워크플로우 실행
    print("-" * 60)
    print("[2] Graph 워크플로우 실행")
    print("    ANALYZE → EVALUATE → DECIDE → REGENERATE → ANALYZE → ...")
    print("-" * 60)
    print()

    # Mock analyze_node to return controlled responses
    call_count = {"count": 0}

    def mock_analyze_node(task=None, **kwargs):
        from ops_agent.graph.state import get_current_workflow_state
        from ops_agent.graph.nodes import _print_step_header, _print_step_result

        state = get_current_workflow_state()
        if not state:
            raise RuntimeError("No workflow state found")

        call_count["count"] += 1
        is_first_call = call_count["count"] == 1

        _print_step_header(
            "ANALYZE",
            f"LLM 에이전트 실행 (시도 {state.attempt + 1}/{state.max_attempts}) [MOCK]"
        )

        if is_first_call:
            response = bad_response
            print("    → 나쁜 응답 반환 (REGENERATE 유도)")
        else:
            response = good_response
            print("    → 좋은 응답 반환 (PASS 유도)")

        # Update state
        state.response = response
        state.tool_results = [mock_tool_result]

        _print_step_result("ANALYZE", {
            "응답 길이": f"{len(response)}자",
            "도구 호출": "1건 (mock)",
        })

        return {
            "text": response,
            "tool_results_count": 1,
        }

    # Run graph with mocked analyze_node
    # Note: Must patch where it's imported (runner.py), not where it's defined (nodes.py)
    with patch("ops_agent.graph.runner.analyze_node", mock_analyze_node):
        graph = OpsAgentGraph(max_attempts=3, verbose=True)
        prompt = "payment-service에서 500 에러 로그 보여줘"
        result = graph.run(prompt)

    # [3] 최종 결과 확인
    print()
    print("-" * 60)
    print("[3] 최종 결과")
    print("-" * 60)
    print(f"  - 상태: {result.final_status.value}")
    print(f"  - 총 시도 횟수: {result.attempt + 1}")
    print(f"  - 최종 판정: {result.verdict.value if result.verdict else 'N/A'}")
    if result.eval_result:
        print(f"  - 최종 점수: {result.eval_result.overall_score:.2f}")
    print()

    # 요약
    print("-" * 60)
    print("[요약] REGENERATE 흐름")
    print("-" * 60)
    print("  1차: ANALYZE → EVALUATE → DECIDE(REGENERATE)")
    print("  2차: REGENERATE → ANALYZE → EVALUATE → DECIDE(PASS) → FINALIZE")
    print()
    if result.attempt > 0:
        print("  ✅ REGENERATE 루프 정상 동작!")
    else:
        print("  ⚠️ REGENERATE 없이 첫 시도에서 PASS")
    print("-" * 60)


def test_7_graph_workflow() -> None:
    """테스트 7: Graph 기반 워크플로우 테스트 (Langfuse 트레이스 포함).

    OpsAgent를 사용하여 Graph 워크플로우 실행.
    Langfuse에 "invoke_agent OpsAgent (Local)" 트레이스 기록.

    흐름:
        ANALYZE → EVALUATE → DECIDE → FINALIZE
                               ↓
                          REGENERATE → ANALYZE (loop)
    """
    from ops_agent.agent import OpsAgent

    print_header("테스트 7: Graph 기반 워크플로우 (Langfuse 트레이스)")
    print("OpsAgent를 사용한 평가 워크플로우 + Langfuse 관측성")
    print()

    # [1] OpsAgent 초기화
    print("-" * 60)
    print("[1] OpsAgent 초기화")
    print("-" * 60)

    agent = OpsAgent(
        enable_evaluation=True,
        max_attempts=2,
        verbose=True,
        session_id="test-manual-session",
        user_id="test-user",
    )
    print(f"  - Session ID: {agent.session_id}")
    print(f"  - User ID: {agent.user_id}")
    print(f"  - Evaluation: {agent.enable_evaluation}")
    print()

    # [2] 워크플로우 실행
    print("-" * 60)
    print("[2] 워크플로우 실행")
    print("-" * 60)

    prompt = "payment-service에서 500 에러 로그 보여줘"
    print(f"  질문: {prompt}")
    print()

    response = agent.invoke(prompt)

    # [3] 최종 결과
    print("-" * 60)
    print("[3] 최종 응답")
    print("-" * 60)

    if response:
        if len(response) > 500:
            print(response[:500] + "\n...")
        else:
            print(response)
    print("-" * 60)

    # [4] Langfuse 안내
    print()
    print("-" * 60)
    print("[4] Langfuse 트레이스 확인")
    print("-" * 60)
    print("  트레이스 이름: invoke_agent OpsAgent (Local)")
    print(f"  Session ID: {agent.session_id}")
    print(f"  User ID: {agent.user_id}")
    print("-" * 60)


def test_8_kb_retrieve() -> None:
    """테스트 8: Knowledge Base 검색 테스트.

    Bedrock KB (Bridge)에 HYBRID 검색으로 기술 문서를 조회합니다.
    KB_MODE=mcp 설정 시 실제 Bedrock API를 호출합니다.

    흐름:
        [1] KB 도구 직접 호출 (kb_retrieve)
        [2] OpsAgent를 통한 KB 질의 (에이전트가 kb_retrieve 도구 자동 선택)
    """
    import json

    from ops_agent.agent import OpsAgent
    from ops_agent.tools.knowledge_base import get_kb_tools

    print_header("테스트 8: Knowledge Base 검색 (Bridge KB)")

    # [1] OpsAgent를 통한 KB 질의
    print("-" * 60)
    print("[1] OpsAgent를 통한 KB 질의 (평가 없음)")
    print("-" * 60)

    agent = OpsAgent(enable_evaluation=False)
    query = "TSS Activation이 뭐야?"
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
    result = json.loads(kb_fn(query=query, category="tss"))

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


def test_9_kb_with_evaluation() -> None:
    """테스트 9: KB 검색 + Graph 평가 워크플로우.

    KB 질의에 대해 전체 Graph 워크플로우를 실행합니다.
    ANALYZE → EVALUATE (CloudWatchChecker + KBChecker) → DECIDE → FINALIZE

    KBChecker가 KB 검색 결과의 핵심 내용이 응답에 반영되었는지 평가합니다.
    """
    from ops_agent.agent import OpsAgent

    print_header("테스트 9: KB 검색 + Graph 평가 워크플로우")
    print("ANALYZE → EVALUATE (KBChecker) → DECIDE → FINALIZE")
    print()

    agent = OpsAgent(
        enable_evaluation=True,
        max_attempts=2,
        verbose=True,
    )

    query = "TSS Activation이 뭐야?"
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
        choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        help="실행할 테스트 번호 (1-9)",
    )
    args = parser.parse_args()

    tests = {
        1: ("CloudWatch 로그 조회", test_1_cloudwatch_logs),
        2: ("Message Injection", test_2_message_injection),
        3: ("CloudWatch 도구 직접 테스트", test_3_tool_only),
        4: ("시스템 프롬프트 확인", test_4_prompt_only),
        5: ("설정 확인", test_5_settings),
        6: ("Graph REGENERATE 테스트", test_6_graph_regeneration),
        7: ("Graph 워크플로우 테스트", test_7_graph_workflow),
        8: ("Knowledge Base 검색 테스트", test_8_kb_retrieve),
        9: ("KB + Graph 평가 워크플로우", test_9_kb_with_evaluation),
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
        print("  uv run python tests/test_manual.py -t 5")
        print()


if __name__ == "__main__":
    main()
