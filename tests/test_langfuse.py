#!/usr/bin/env python
"""Langfuse 트레이스 테스트 (로컬 Strands).

사용법:
    uv run python tests/test_langfuse.py --prompt "Hello test"
    uv run python tests/test_langfuse.py --interactive
    uv run python tests/test_langfuse.py -i
"""

import argparse

from ops_agent.config import get_settings
get_settings.cache_clear()

from ops_agent.agent import OpsAgent


def main():
    parser = argparse.ArgumentParser(description="Langfuse 트레이스 테스트 (로컬 Strands)")
    parser.add_argument("--prompt", "-p", type=str, help="테스트 프롬프트")
    parser.add_argument("--interactive", "-i", action="store_true", help="대화형 모드")
    parser.add_argument("--session", "-s", type=str, default="local-langfuse-test", help="세션 ID")
    parser.add_argument("--user", "-u", type=str, default="test-user", help="사용자 ID")
    args = parser.parse_args()

    agent = OpsAgent(
        enable_evaluation=False,
        session_id=args.session,
        user_id=args.user,
    )

    print("=" * 60)
    print("Langfuse Local Strands Test")
    print("=" * 60)
    print(f"Session: {args.session}")
    print(f"User: {args.user}")
    print(f"Trace name: invoke_agent OpsAgent (Local)")
    print("=" * 60)
    print()

    if args.interactive:
        # Interactive mode
        print("대화형 모드 (종료: quit, exit, q)")
        print()
        while True:
            try:
                prompt = input("You: ").strip()
                if not prompt:
                    continue
                if prompt.lower() in ["quit", "exit", "q"]:
                    print("Bye!")
                    break

                response = agent.invoke(prompt)
                print()
                print("Agent:")
                print(response)
                print()
            except KeyboardInterrupt:
                print("\nBye!")
                break
    elif args.prompt:
        # Single prompt mode
        print(f"Prompt: {args.prompt}")
        print()
        response = agent.invoke(args.prompt)
        print("Response:")
        print(response)
    else:
        # Default test
        prompt = "Hello, this is a Langfuse test"
        print(f"Prompt: {prompt}")
        print()
        response = agent.invoke(prompt)
        print("Response:")
        print(response)

    print()
    print("=" * 60)
    print("Check Langfuse for trace: invoke_agent OpsAgent (Local)")
    print("=" * 60)


if __name__ == "__main__":
    main()
