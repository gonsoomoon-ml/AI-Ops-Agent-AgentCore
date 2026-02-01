#!/usr/bin/env python3
"""AgentCore Runtime에서 OpsAgent 삭제.

배포된 에이전트와 관련 리소스를 정리합니다.

사용법:
    uv run python scripts/cleanup.py
    uv run python scripts/cleanup.py --keep-ecr
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_agent_info(region: str) -> dict:
    """SSM 또는 메타데이터 파일에서 에이전트 정보 조회."""
    ssm = boto3.client("ssm", region_name=region)

    agent_info = {}

    # SSM에서 조회 시도
    try:
        response = ssm.get_parameter(Name="/app/opsagent/agentcore/runtime_arn")
        agent_info["agent_arn"] = response["Parameter"]["Value"]
    except:
        pass

    try:
        response = ssm.get_parameter(Name="/app/opsagent/agentcore/runtime_id")
        agent_info["agent_id"] = response["Parameter"]["Value"]
    except:
        pass

    # 메타데이터 파일에서 조회 시도
    if not agent_info:
        script_dir = Path(__file__).parent
        metadata_file = script_dir / ".deployment_metadata.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            agent_info = metadata

    return agent_info


def delete_agent(agent_id: str, region: str) -> bool:
    """AgentCore Runtime에서 에이전트 삭제."""
    client = boto3.client("bedrock-agentcore-control", region_name=region)

    try:
        logger.info(f"에이전트 삭제 중: {agent_id}")
        client.delete_agent_runtime(agentRuntimeId=agent_id)
        logger.info("에이전트 삭제 완료")
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            logger.warning("에이전트를 찾을 수 없음 (이미 삭제됨?)")
            return True
        else:
            logger.error(f"에이전트 삭제 실패: {e}")
            return False


def delete_ssm_parameters(region: str) -> None:
    """SSM 파라미터 삭제."""
    ssm = boto3.client("ssm", region_name=region)

    params = [
        "/app/opsagent/agentcore/runtime_arn",
        "/app/opsagent/agentcore/runtime_id",
    ]

    for param in params:
        try:
            ssm.delete_parameter(Name=param)
            logger.info(f"SSM 파라미터 삭제: {param}")
        except ssm.exceptions.ParameterNotFound:
            pass
        except Exception as e:
            logger.warning(f"{param} 삭제 실패: {e}")


def delete_ecr_repository(ecr_uri: str, region: str) -> None:
    """ECR 리포지토리 삭제."""
    if not ecr_uri:
        return

    ecr = boto3.client("ecr", region_name=region)

    # URI에서 리포지토리 이름 추출
    # 형식: 123456789012.dkr.ecr.us-east-1.amazonaws.com/repo-name:tag
    try:
        repo_name = ecr_uri.split("/")[-1].split(":")[0]

        logger.info(f"ECR 리포지토리 삭제 중: {repo_name}")
        ecr.delete_repository(repositoryName=repo_name, force=True)
        logger.info("ECR 리포지토리 삭제 완료")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "RepositoryNotFoundException":
            logger.warning("ECR 리포지토리를 찾을 수 없음 (이미 삭제됨?)")
        else:
            logger.warning(f"ECR 리포지토리 삭제 실패: {e}")


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(
        description="AgentCore Runtime에서 OpsAgent 삭제",
    )

    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS 리전 (기본값: us-east-1)",
    )

    parser.add_argument(
        "--keep-ecr",
        action="store_true",
        help="ECR 리포지토리 유지 (컨테이너 이미지 삭제 안 함)",
    )

    parser.add_argument(
        "--keep-ssm",
        action="store_true",
        help="SSM 파라미터 유지",
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="확인 프롬프트 생략",
    )

    args = parser.parse_args()

    # 에이전트 정보 조회
    agent_info = get_agent_info(args.region)

    if not agent_info:
        logger.error("배포된 에이전트를 찾을 수 없음")
        sys.exit(1)

    agent_id = agent_info.get("agent_id")
    agent_arn = agent_info.get("agent_arn")
    ecr_uri = agent_info.get("ecr_uri")

    # 확인
    if not args.force:
        print()
        print("=" * 60)
        print("경고: 다음 리소스가 삭제됩니다:")
        print("=" * 60)
        print(f"  Agent ID:  {agent_id}")
        print(f"  Agent ARN: {agent_arn}")
        if not args.keep_ecr and ecr_uri:
            print(f"  ECR URI:   {ecr_uri}")
        if not args.keep_ssm:
            print("  SSM 파라미터")
        print("=" * 60)
        print()

        confirm = input("계속하시겠습니까? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("취소됨.")
            sys.exit(0)

    # 에이전트 삭제
    if agent_id:
        delete_agent(agent_id, args.region)

    # SSM 파라미터 삭제
    if not args.keep_ssm:
        delete_ssm_parameters(args.region)

    # ECR 리포지토리 삭제
    if not args.keep_ecr:
        delete_ecr_repository(ecr_uri, args.region)

    # 로컬 메타데이터 삭제
    script_dir = Path(__file__).parent
    metadata_file = script_dir / ".deployment_metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()
        logger.info("로컬 메타데이터 파일 삭제")

    print()
    print("=" * 60)
    print("정리 완료")
    print("=" * 60)
    print()
    print("참고: IAM 역할을 삭제하려면 다음을 실행하세요:")
    print("  aws cloudformation delete-stack --stack-name OpsAgentInfraStack")
    print()


if __name__ == "__main__":
    main()
