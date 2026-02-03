#!/usr/bin/env python3
"""OpsAgent를 Amazon Bedrock AgentCore Runtime에 배포.

bedrock-agentcore-starter-toolkit을 사용하여 에이전트를 배포합니다.
Docker 컨테이너화 및 OTEL instrumentation이 자동으로 처리됩니다.

참조:
    - amazon-bedrock-agentcore-samples/03-integrations/observability/simple-dual-observability/

사용법:
    uv run python scripts/deploy.py
    uv run python scripts/deploy.py --name my-ops-agent
    uv run python scripts/deploy.py --region us-west-2
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

# 프로젝트 루트의 .env 파일 로드 (settings가 올바른 값을 읽을 수 있도록)
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
dotenv_path = project_root / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path, override=True)

# settings 캐시 초기화 후 telemetry 임포트
from ops_agent.config.settings import get_settings
get_settings.cache_clear()

from ops_agent.telemetry import get_agentcore_observability_env_vars

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def validate_environment() -> None:
    """필수 환경 및 의존성 검증."""
    try:
        import boto3
        from bedrock_agentcore_starter_toolkit import Runtime

        logger.info("필수 패키지 확인 완료: boto3, bedrock-agentcore-starter-toolkit")

    except ImportError as e:
        logger.error(f"필수 패키지 누락: {e}")
        logger.error("설치: pip install bedrock-agentcore-starter-toolkit")
        sys.exit(1)

    # AWS 자격 증명 검증
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        logger.info(f"AWS 계정: {identity['Account']}")
        logger.info(f"AWS ID: {identity['Arn']}")

    except Exception as e:
        logger.error(f"AWS 자격 증명 검증 실패: {e}")
        logger.error("실행: aws configure")
        sys.exit(1)


def copy_source_to_runtime(runtime_dir: Path, project_root: Path) -> Path:
    """Docker 빌드를 위해 src/ops_agent를 runtime 디렉토리로 복사.

    Args:
        runtime_dir: agentcore/runtime/ 경로
        project_root: 프로젝트 루트 경로

    Returns:
        복사된 ops_agent 디렉토리 경로
    """
    src_ops_agent = project_root / "src" / "ops_agent"
    dest_ops_agent = runtime_dir / "ops_agent"

    if not src_ops_agent.exists():
        logger.error(f"소스 디렉토리를 찾을 수 없음: {src_ops_agent}")
        sys.exit(1)

    # 기존 복사본이 있으면 삭제
    if dest_ops_agent.exists():
        logger.info(f"기존 복사본 삭제: {dest_ops_agent}")
        shutil.rmtree(dest_ops_agent)

    # 소스를 runtime으로 복사
    logger.info(f"복사 중: {src_ops_agent} -> {dest_ops_agent}")
    shutil.copytree(src_ops_agent, dest_ops_agent)

    return dest_ops_agent


def cleanup_runtime_copy(dest_ops_agent: Path) -> None:
    """배포 후 runtime 디렉토리에서 복사된 소스 삭제."""
    if dest_ops_agent.exists():
        logger.info(f"정리 중: {dest_ops_agent}")
        shutil.rmtree(dest_ops_agent)


def get_execution_role_arn(region: str) -> str:
    """SSM Parameter Store에서 실행 역할 ARN 조회."""
    import boto3
    from botocore.exceptions import ClientError

    ssm = boto3.client("ssm", region_name=region)

    try:
        response = ssm.get_parameter(Name="/app/opsagent/agentcore/runtime_iam_role")
        role_arn = response["Parameter"]["Value"]
        logger.info(f"실행 역할: {role_arn}")
        return role_arn

    except ClientError as e:
        if e.response["Error"]["Code"] == "ParameterNotFound":
            logger.error("SSM에서 실행 역할을 찾을 수 없음")
            logger.error("실행: ./agentcore/deploy_infra.sh")
        else:
            logger.error(f"실행 역할 조회 실패: {e}")
        sys.exit(1)


def save_ssm_parameter(name: str, value: str, region: str) -> None:
    """SSM Parameter Store에 값 저장."""
    import boto3

    ssm = boto3.client("ssm", region_name=region)
    ssm.put_parameter(
        Name=name,
        Value=value,
        Type="String",
        Description=f"OpsAgent AgentCore: {name.split('/')[-1]}",
        Overwrite=True,
    )
    logger.info(f"SSM 저장 완료: {name}")


def deploy_agent(
    agent_name: str,
    region: str,
    execution_role_arn: str,
    auto_update: bool = False,
    keep_source_copy: bool = False,
) -> dict:
    """AgentCore Runtime에 에이전트 배포.

    Args:
        agent_name: 배포할 에이전트 이름
        region: AWS 리전
        execution_role_arn: 실행 IAM 역할 ARN
        auto_update: 기존 에이전트 자동 업데이트 여부
        keep_source_copy: 배포 후 runtime/에 ops_agent 복사본 유지 여부

    Returns:
        배포 정보 딕셔너리
    """
    from bedrock_agentcore_starter_toolkit import Runtime

    # 경로 설정
    script_dir = Path(__file__).parent
    agentcore_dir = script_dir.parent
    runtime_dir = agentcore_dir / "runtime"
    project_root = agentcore_dir.parent

    # 경로 검증
    if not runtime_dir.exists():
        logger.error(f"Runtime 디렉토리를 찾을 수 없음: {runtime_dir}")
        sys.exit(1)

    entrypoint_path = runtime_dir / "entrypoint.py"
    requirements_path = runtime_dir / "requirements.txt"

    if not entrypoint_path.exists():
        logger.error(f"Entrypoint를 찾을 수 없음: {entrypoint_path}")
        sys.exit(1)

    if not requirements_path.exists():
        logger.error(f"Requirements 파일을 찾을 수 없음: {requirements_path}")
        sys.exit(1)

    entrypoint = str(entrypoint_path)
    requirements = str(requirements_path)

    logger.info("=" * 60)
    logger.info("AGENTCORE 배포")
    logger.info("=" * 60)
    logger.info(f"에이전트 이름: {agent_name}")
    logger.info(f"리전:         {region}")
    logger.info(f"Entrypoint:   {entrypoint}")
    logger.info(f"Requirements: {requirements}")
    logger.info("=" * 60)

    # Docker 빌드를 위해 소스 코드를 runtime 디렉토리로 복사
    logger.info("")
    logger.info("Docker 빌드를 위한 소스 코드 준비 중...")
    dest_ops_agent = copy_source_to_runtime(runtime_dir, project_root)

    # 배포를 위해 runtime 디렉토리로 이동
    original_dir = os.getcwd()
    os.chdir(runtime_dir)

    deployment_success = False
    try:
        # Runtime 초기화
        runtime = Runtime()

        # Observability 환경 변수 설정 (configure 전에 필요)
        env_vars = get_agentcore_observability_env_vars()
        if env_vars:
            logger.info(f"Observability 환경 변수: {list(env_vars.keys())}")

        # 배포 설정 (authorizer 없음 = IAM SigV4 인증 사용)
        logger.info("에이전트 배포 설정 중...")
        # Langfuse 사용 시 AWS ADOT 비활성화 필요
        disable_otel = bool(env_vars.get("DISABLE_ADOT_OBSERVABILITY"))

        runtime.configure(
            entrypoint="entrypoint.py",
            execution_role=execution_role_arn,
            auto_create_ecr=True,
            requirements_file="requirements.txt",
            region=region,
            agent_name=agent_name,
            disable_otel=disable_otel,  # Langfuse 사용 시 AWS ADOT 비활성화
            # authorizer_configuration 없음 = IAM SigV4 기본 인증
        )

        # 배포 시작
        logger.info("AgentCore Runtime에 에이전트 배포 중...")
        logger.info("수행 작업:")
        logger.info("  1. Docker 컨테이너 빌드")
        logger.info("  2. Amazon ECR로 푸시")
        logger.info("  3. AgentCore Runtime에 배포")
        logger.info("약 5-10분 소요...")
        logger.info("")

        launch_result = runtime.launch(auto_update_on_conflict=auto_update, env_vars=env_vars)

        # 결과 추출
        deployment_info = {
            "agent_id": launch_result.agent_id,
            "agent_arn": launch_result.agent_arn,
            "ecr_uri": launch_result.ecr_uri,
            "region": region,
            "agent_name": agent_name,
        }

        deployment_success = True
        return deployment_info

    finally:
        os.chdir(original_dir)
        # 성공 시에만 복사본 정리 (실패 시 디버깅을 위해 유지)
        if deployment_success and not keep_source_copy:
            cleanup_runtime_copy(dest_ops_agent)
        elif not deployment_success:
            logger.info(f"디버깅을 위해 소스 복사본 유지: {dest_ops_agent}")


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(
        description="OpsAgent를 Amazon Bedrock AgentCore Runtime에 배포",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
    # 기본 설정으로 배포
    uv run python scripts/deploy.py

    # 사용자 지정 이름으로 배포
    uv run python scripts/deploy.py --name my-ops-agent

    # 특정 리전에 배포
    uv run python scripts/deploy.py --region us-west-2

    # 기존 에이전트 업데이트
    uv run python scripts/deploy.py --auto-update
""",
    )

    parser.add_argument(
        "--name",
        default="ops_ai_agent",
        help="에이전트 이름 (기본값: ops_ai_agent). 문자로 시작, 문자/숫자/밑줄만 허용, 1-48자",
    )

    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS 리전 (기본값: us-east-1)",
    )

    parser.add_argument(
        "--auto-update",
        action="store_true",
        help="기존 에이전트가 있으면 자동 업데이트",
    )

    parser.add_argument(
        "--keep-source-copy",
        action="store_true",
        help="배포 후 runtime/에 ops_agent 복사본 유지 (디버깅용)",
    )

    args = parser.parse_args()

    # 환경 검증
    validate_environment()

    # 실행 역할 조회
    execution_role_arn = get_execution_role_arn(args.region)

    # 배포
    deployment_info = deploy_agent(
        agent_name=args.name,
        region=args.region,
        execution_role_arn=execution_role_arn,
        auto_update=args.auto_update,
        keep_source_copy=args.keep_source_copy,
    )

    # 배포 정보를 SSM에 저장
    save_ssm_parameter(
        "/app/opsagent/agentcore/runtime_arn",
        deployment_info["agent_arn"],
        args.region,
    )
    save_ssm_parameter(
        "/app/opsagent/agentcore/runtime_id",
        deployment_info["agent_id"],
        args.region,
    )

    # 로컬 파일에 저장
    script_dir = Path(__file__).parent
    metadata_file = script_dir / ".deployment_metadata.json"
    metadata_file.write_text(json.dumps(deployment_info, indent=2))

    # 요약 출력
    logger.info("")
    logger.info("=" * 60)
    logger.info("배포 완료!")
    logger.info("=" * 60)
    logger.info(f"Agent ID:  {deployment_info['agent_id']}")
    logger.info(f"Agent ARN: {deployment_info['agent_arn']}")
    logger.info(f"ECR URI:   {deployment_info['ecr_uri']}")
    logger.info("")
    logger.info("다음 단계:")
    logger.info("  1. 테스트: uv run python scripts/invoke.py --prompt 'test'")
    logger.info("  2. 로그: CloudWatch Logs 확인")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
