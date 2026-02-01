#!/usr/bin/env python3
"""AgentCore Runtime 스트리밍 클라이언트.

사용법:
    uv run python scripts/invoke.py --prompt "payment-service 에러 보여줘"
    uv run python scripts/invoke.py --test simple
    uv run python scripts/invoke.py --test simple --verbose
    uv run python scripts/invoke.py --interactive
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from util import AgentCoreClient, Metrics

# =============================================================================
# Configuration
# =============================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TEST_PROMPTS = {
    "error": "payment-service에서 최근 500 에러 로그 보여줘",
    "timeout": "Lambda 함수에서 timeout 에러 찾아줘",
    "analysis": "order-service의 최근 1시간 에러 분석해줘",
    "simple": "안녕하세요, 테스트입니다.",
}

SSM_PARAM = "/app/opsagent/agentcore/runtime_arn"
METADATA_FILE = ".deployment_metadata.json"


# =============================================================================
# ARN Resolution
# =============================================================================


def resolve_arn(region: str, script_dir: Path, provided: str | None = None) -> str:
    """에이전트 ARN 조회.

    순서:
        1. 직접 제공된 ARN
        2. SSM Parameter Store
        3. 로컬 메타데이터 파일

    Args:
        region: AWS 리전
        script_dir: 스크립트 디렉토리 경로
        provided: 직접 제공된 ARN (선택)

    Returns:
        에이전트 ARN

    Raises:
        ValueError: ARN을 찾을 수 없는 경우
    """
    if provided:
        return provided

    # SSM
    try:
        ssm = boto3.client("ssm", region_name=region)
        return ssm.get_parameter(Name=SSM_PARAM)["Parameter"]["Value"]
    except ClientError:
        pass

    # Metadata file
    metadata_file = script_dir / METADATA_FILE
    if metadata_file.exists():
        try:
            return json.loads(metadata_file.read_text()).get("agent_arn")
        except (json.JSONDecodeError, OSError):
            pass

    raise ValueError("에이전트 ARN을 찾을 수 없음. 먼저 배포하세요.")


# =============================================================================
# Run Modes
# =============================================================================


def run_prompt(client: AgentCoreClient, prompt: str, raw: bool = False, verbose: bool = False) -> None:
    """단일 프롬프트 실행.

    Args:
        client: AgentCore 클라이언트
        prompt: 사용자 프롬프트
        raw: 원시 SSE 이벤트 출력 여부
        verbose: 토큰별 타이밍 출력 여부
    """
    session_id = str(uuid.uuid4())
    metrics = Metrics()

    print()
    print("=" * 70)
    mode = "[RAW]" if raw else "[VERBOSE]" if verbose else ""
    print(f"AGENT RESPONSE {mode}".strip())
    print("=" * 70)
    print()

    for token in client.stream(prompt, session_id, raw):
        metrics.record_token()

        if raw:
            print(token)
        elif verbose:
            elapsed = time.time() - metrics.start
            print(f"[{elapsed:6.2f}s] #{metrics.tokens:3d} {repr(token)}")
        else:
            print(token, end="", flush=True)

    metrics.finish()

    if not raw and not verbose:
        print()

    print()
    print("-" * 70)
    print(f"Session: {session_id}")
    print(f"Metrics: {metrics}")
    print("=" * 70)


def run_interactive(client: AgentCoreClient, raw: bool = False) -> None:
    """대화형 모드.

    Args:
        client: AgentCore 클라이언트
        raw: 원시 SSE 이벤트 출력 여부
    """
    session_id = str(uuid.uuid4())

    print()
    print("=" * 70)
    print("Interactive Mode")
    print("=" * 70)
    print("Commands: 'quit' to exit, 'test' for test prompts")
    print(f"Session: {session_id}")
    print("=" * 70)
    print()

    while True:
        try:
            prompt = input("You: ").strip()

            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit", "q"):
                print("Bye!")
                break
            if prompt.lower() == "test":
                print("\nTest prompts:")
                for k, v in TEST_PROMPTS.items():
                    print(f"  {k}: {v}")
                print()
                continue

            print("\nAgent: ", end="", flush=True)
            metrics = Metrics()

            for token in client.stream(prompt, session_id, raw):
                metrics.record_token()
                if raw:
                    print(token)
                else:
                    print(token, end="", flush=True)

            metrics.finish()
            print(f"\n  [{metrics}]\n")

        except KeyboardInterrupt:
            print("\n\nBye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(
        description="AgentCore Runtime 스트리밍 클라이언트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --prompt "payment-service 에러 보여줘"
    %(prog)s --test simple
    %(prog)s --test simple --verbose
    %(prog)s --interactive
""",
    )

    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--agent-arn", help="Agent ARN (auto-detect if not provided)")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--test", choices=list(TEST_PROMPTS.keys()), help="Run test prompt")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--raw", action="store_true", help="Show raw SSE events")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show token-by-token with timing")

    args = parser.parse_args()

    # Resolve ARN
    try:
        arn = resolve_arn(args.region, Path(__file__).parent, args.agent_arn)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"Agent: {arn}")
    logger.info(f"Region: {args.region}")

    client = AgentCoreClient(arn, args.region)

    # Run
    if args.interactive:
        run_interactive(client, args.raw)
    elif args.test:
        prompt = TEST_PROMPTS[args.test]
        logger.info(f"Test: {args.test}")
        run_prompt(client, prompt, args.raw, args.verbose)
    elif args.prompt:
        run_prompt(client, args.prompt, args.raw, args.verbose)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
