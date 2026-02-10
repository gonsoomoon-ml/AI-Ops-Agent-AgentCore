#!/usr/bin/env python3
"""AgentCore Runtime에서 OpsAgent 삭제.

배포된 에이전트와 관련 리소스를 정리합니다.

사용법:
    uv run python scripts/cleanup.py              # 기본 정리 (런타임, SSM, ECR)
    uv run python scripts/cleanup.py --keep-ecr   # ECR 유지
    uv run python scripts/cleanup.py --all        # 모든 리소스 삭제
    uv run python scripts/cleanup.py --all -f     # 확인 생략
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 기본값
DEFAULT_AGENT_NAME = "ops_ai_agent"
DEFAULT_STACK_NAME = "OpsAgentInfraStack"


def get_agent_info(region: str) -> dict:
    """SSM 또는 메타데이터 파일에서 에이전트 정보 조회."""
    ssm = boto3.client("ssm", region_name=region)

    agent_info = {}

    # SSM에서 조회 시도
    try:
        response = ssm.get_parameter(Name="/app/opsagent/agentcore/runtime_arn")
        agent_info["agent_arn"] = response["Parameter"]["Value"]
    except Exception:
        pass

    try:
        response = ssm.get_parameter(Name="/app/opsagent/agentcore/runtime_id")
        agent_info["agent_id"] = response["Parameter"]["Value"]
    except Exception:
        pass

    # 메타데이터 파일에서 조회 시도
    metadata = _load_deployment_metadata()
    if not agent_info and metadata:
        agent_info = metadata
    elif metadata:
        # SSM에 없는 필드를 메타데이터에서 보충
        for key in ("ecr_uri", "agent_name"):
            if key not in agent_info and key in metadata:
                agent_info[key] = metadata[key]

    return agent_info


def _load_deployment_metadata() -> dict | None:
    """로컬 .deployment_metadata.json 파일 로드."""
    script_dir = Path(__file__).parent
    metadata_file = script_dir / ".deployment_metadata.json"
    if metadata_file.exists():
        return json.loads(metadata_file.read_text())
    return None


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


def delete_ssm_parameters(region: str, include_iam_role: bool = False) -> None:
    """SSM 파라미터 삭제."""
    ssm = boto3.client("ssm", region_name=region)

    params = [
        "/app/opsagent/agentcore/runtime_arn",
        "/app/opsagent/agentcore/runtime_id",
    ]
    if include_iam_role:
        params.append("/app/opsagent/agentcore/runtime_iam_role")

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


def delete_codebuild_resources(agent_name: str, region: str) -> None:
    """CodeBuild 프로젝트, IAM 역할, S3 소스 버킷 삭제."""
    codebuild = boto3.client("codebuild", region_name=region)
    iam = boto3.client("iam")
    s3 = boto3.client("s3", region_name=region)
    sts = boto3.client("sts")

    account_id = sts.get_caller_identity()["Account"]

    # 1. CodeBuild 프로젝트 삭제
    project_name = f"bedrock-agentcore-{agent_name}-builder"
    try:
        codebuild.delete_project(name=project_name)
        logger.info(f"CodeBuild 프로젝트 삭제: {project_name}")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            logger.warning(f"CodeBuild 프로젝트를 찾을 수 없음: {project_name}")
        else:
            logger.warning(f"CodeBuild 프로젝트 삭제 실패: {e}")

    # 2. CodeBuild IAM 역할 삭제
    #    역할 이름 형식: AmazonBedrockAgentCoreSDKCodeBuild-{region}-{agent_name}
    role_name = f"AmazonBedrockAgentCoreSDKCodeBuild-{region}-{agent_name}"
    _delete_iam_role(iam, role_name)

    # 3. CodeBuild S3 소스 버킷 삭제
    bucket_name = f"bedrock-agentcore-codebuild-sources-{account_id}-{region}"
    _delete_s3_bucket(s3, bucket_name)


def _delete_iam_role(iam, role_name: str) -> None:
    """IAM 역할과 연결된 정책을 삭제."""
    try:
        # 인라인 정책 삭제
        inline_policies = iam.list_role_policies(RoleName=role_name)
        for policy_name in inline_policies.get("PolicyNames", []):
            iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            logger.info(f"  인라인 정책 삭제: {policy_name}")

        # 관리형 정책 분리
        attached_policies = iam.list_attached_role_policies(RoleName=role_name)
        for policy in attached_policies.get("AttachedPolicies", []):
            iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])
            logger.info(f"  관리형 정책 분리: {policy['PolicyName']}")

        # 역할 삭제
        iam.delete_role(RoleName=role_name)
        logger.info(f"IAM 역할 삭제: {role_name}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "NoSuchEntity":
            logger.warning(f"IAM 역할을 찾을 수 없음: {role_name}")
        else:
            logger.warning(f"IAM 역할 삭제 실패: {e}")


def _delete_s3_bucket(s3, bucket_name: str) -> None:
    """S3 버킷의 모든 객체와 버킷을 삭제."""
    try:
        # 버킷 내 모든 객체 삭제
        paginator = s3.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket_name):
            objects_to_delete = []
            for version in page.get("Versions", []):
                objects_to_delete.append(
                    {"Key": version["Key"], "VersionId": version["VersionId"]}
                )
            for marker in page.get("DeleteMarkers", []):
                objects_to_delete.append(
                    {"Key": marker["Key"], "VersionId": marker["VersionId"]}
                )
            if objects_to_delete:
                s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": objects_to_delete},
                )

        s3.delete_bucket(Bucket=bucket_name)
        logger.info(f"S3 버킷 삭제: {bucket_name}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchBucket", "404"):
            logger.warning(f"S3 버킷을 찾을 수 없음: {bucket_name}")
        else:
            logger.warning(f"S3 버킷 삭제 실패: {e}")


def delete_knowledge_bases(region: str) -> None:
    """datasets.yaml에 정의된 모든 Knowledge Base와 관련 리소스 삭제.

    각 KB에 대해 삭제하는 리소스:
      - Bedrock KB data source + KB 자체
      - OpenSearch Serverless collection + policies (encryption, network, access)
      - S3 데이터 버킷 (KB 문서 저장용)
      - IAM 실행 역할 + 정책
      - SSM 파라미터 ({kb_name}-kb-id)
    """
    # datasets.yaml 로드
    datasets_yaml = (
        Path(__file__).parent.parent.parent / "rag_pipeline" / "datasets.yaml"
    )
    if not datasets_yaml.exists():
        logger.warning(f"datasets.yaml을 찾을 수 없음: {datasets_yaml}")
        return

    with open(datasets_yaml) as f:
        config = yaml.safe_load(f)

    datasets = config.get("datasets", {})
    if not datasets:
        logger.info("datasets.yaml에 데이터셋 없음")
        return

    bedrock_agent = boto3.client("bedrock-agent", region_name=region)
    aoss = boto3.client("opensearchserverless", region_name=region)
    iam = boto3.client("iam")
    s3 = boto3.client("s3", region_name=region)
    ssm = boto3.client("ssm", region_name=region)

    # Bedrock KB 목록 조회 (이름 → ID 매핑)
    try:
        kb_list = bedrock_agent.list_knowledge_bases(maxResults=100)
        kb_name_to_id = {
            kb["name"]: kb["knowledgeBaseId"]
            for kb in kb_list.get("knowledgeBaseSummaries", [])
        }
    except ClientError as e:
        logger.warning(f"Knowledge Base 목록 조회 실패: {e}")
        return

    for dataset_name, ds_config in datasets.items():
        kb_name = ds_config.get("kb_name")
        if not kb_name:
            continue

        kb_id = kb_name_to_id.get(kb_name)
        if not kb_id:
            logger.info(f"[{dataset_name}] KB '{kb_name}'을 찾을 수 없음 (미생성 또는 이미 삭제됨)")
            continue

        logger.info(f"[{dataset_name}] KB 삭제 중: {kb_name} ({kb_id})")

        # KB 상세 정보 조회
        try:
            kb_details = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
            kb_info = kb_details["knowledgeBase"]
            kb_role_name = kb_info["roleArn"].split("/")[-1]

            oss_config = kb_info["storageConfiguration"].get(
                "opensearchServerlessConfiguration", {}
            )
            collection_arn = oss_config.get("collectionArn", "")
            collection_id = collection_arn.split("/")[-1] if collection_arn else None
        except ClientError as e:
            logger.warning(f"  KB 상세 조회 실패: {e}")
            continue

        # 1. Data Source 삭제
        try:
            ds_list = bedrock_agent.list_data_sources(
                knowledgeBaseId=kb_id, maxResults=100
            )
            for ds in ds_list.get("dataSourceSummaries", []):
                ds_id = ds["dataSourceId"]
                # S3 버킷 이름 추출 (삭제용)
                try:
                    ds_detail = bedrock_agent.get_data_source(
                        dataSourceId=ds_id, knowledgeBaseId=kb_id
                    )
                    bucket_arn = (
                        ds_detail["dataSource"]["dataSourceConfiguration"]
                        .get("s3Configuration", {})
                        .get("bucketArn", "")
                    )
                    kb_bucket_name = bucket_arn.replace("arn:aws:s3:::", "") if bucket_arn else None
                except Exception:
                    kb_bucket_name = None

                bedrock_agent.delete_data_source(
                    dataSourceId=ds_id, knowledgeBaseId=kb_id
                )
                logger.info(f"  Data Source 삭제: {ds_id}")

                # S3 버킷 삭제
                if kb_bucket_name:
                    _delete_s3_bucket(s3, kb_bucket_name)
        except ClientError as e:
            logger.warning(f"  Data Source 삭제 실패: {e}")

        # 2. Knowledge Base 삭제
        try:
            bedrock_agent.delete_knowledge_base(knowledgeBaseId=kb_id)
            logger.info(f"  Knowledge Base 삭제: {kb_id}")
        except ClientError as e:
            logger.warning(f"  Knowledge Base 삭제 실패: {e}")

        # 3. OpenSearch Serverless 리소스 삭제
        if collection_id:
            try:
                aoss.delete_collection(id=collection_id)
                logger.info(f"  OpenSearch 컬렉션 삭제: {collection_id}")
            except ClientError as e:
                logger.warning(f"  OpenSearch 컬렉션 삭제 실패: {e}")

        # AOSS 정책 삭제 (kb_name으로 시작하는 것들)
        for policy_type in ("encryption", "network"):
            try:
                policies = aoss.list_security_policies(
                    maxResults=100, type=policy_type
                )
                for p in policies.get("securityPolicySummaries", []):
                    if p["name"].startswith(kb_name):
                        aoss.delete_security_policy(type=policy_type, name=p["name"])
                        logger.info(f"  AOSS {policy_type} 정책 삭제: {p['name']}")
            except ClientError as e:
                logger.warning(f"  AOSS {policy_type} 정책 삭제 실패: {e}")

        try:
            access_policies = aoss.list_access_policies(maxResults=100, type="data")
            for p in access_policies.get("accessPolicySummaries", []):
                if p["name"].startswith(kb_name):
                    aoss.delete_access_policy(type="data", name=p["name"])
                    logger.info(f"  AOSS access 정책 삭제: {p['name']}")
        except ClientError as e:
            logger.warning(f"  AOSS access 정책 삭제 실패: {e}")

        # 4. IAM 실행 역할 + 정책 삭제
        _delete_iam_role(iam, kb_role_name)

        # 5. SSM 파라미터 삭제
        try:
            ssm.delete_parameter(Name=f"{kb_name}-kb-id")
            logger.info(f"  SSM 파라미터 삭제: {kb_name}-kb-id")
        except ssm.exceptions.ParameterNotFound:
            pass
        except ClientError as e:
            logger.warning(f"  SSM 파라미터 삭제 실패: {e}")

        logger.info(f"[{dataset_name}] KB '{kb_name}' 삭제 완료")


def delete_log_groups(agent_id: str, region: str) -> None:
    """AgentCore 관련 CloudWatch 로그 그룹 삭제."""
    if not agent_id:
        return

    logs = boto3.client("logs", region_name=region)
    prefix = "/aws/bedrock-agentcore/runtimes/"

    try:
        paginator = logs.get_paginator("describe_log_groups")
        deleted_count = 0

        for page in paginator.paginate(logGroupNamePrefix=prefix):
            for log_group in page.get("logGroups", []):
                name = log_group["logGroupName"]
                try:
                    logs.delete_log_group(logGroupName=name)
                    logger.info(f"로그 그룹 삭제: {name}")
                    deleted_count += 1
                except ClientError as e:
                    logger.warning(f"로그 그룹 삭제 실패 ({name}): {e}")

        if deleted_count == 0:
            logger.info("삭제할 AgentCore 로그 그룹 없음")

    except ClientError as e:
        logger.warning(f"로그 그룹 조회 실패: {e}")


def delete_cloudformation_stack(stack_name: str, region: str) -> None:
    """CloudFormation 스택 삭제 (완료까지 대기)."""
    cfn = boto3.client("cloudformation", region_name=region)

    try:
        # 스택 존재 확인
        cfn.describe_stacks(StackName=stack_name)
    except ClientError as e:
        if "does not exist" in str(e):
            logger.warning(f"CloudFormation 스택을 찾을 수 없음: {stack_name}")
            return
        raise

    logger.info(f"CloudFormation 스택 삭제 중: {stack_name}")
    cfn.delete_stack(StackName=stack_name)

    # 삭제 완료 대기
    logger.info("스택 삭제 완료 대기 중...")
    waiter = cfn.get_waiter("stack_delete_complete")
    try:
        waiter.wait(
            StackName=stack_name,
            WaiterConfig={"Delay": 10, "MaxAttempts": 60},
        )
        logger.info("CloudFormation 스택 삭제 완료")
    except Exception as e:
        logger.error(f"CloudFormation 스택 삭제 대기 실패: {e}")
        logger.error("AWS 콘솔에서 스택 상태를 확인하세요.")


def delete_local_files() -> None:
    """로컬 배포 관련 파일 삭제."""
    script_dir = Path(__file__).parent
    agentcore_dir = script_dir.parent
    runtime_dir = agentcore_dir / "runtime"

    # .deployment_metadata.json
    metadata_file = script_dir / ".deployment_metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()
        logger.info(f"로컬 파일 삭제: {metadata_file.name}")

    # .bedrock_agentcore.yaml
    agentcore_yaml = runtime_dir / ".bedrock_agentcore.yaml"
    if agentcore_yaml.exists():
        agentcore_yaml.unlink()
        logger.info(f"로컬 파일 삭제: {agentcore_yaml.name}")


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

    parser.add_argument(
        "--all",
        action="store_true",
        dest="delete_all",
        help="모든 리소스 삭제 (AgentCore 런타임, KB, CodeBuild, CloudFormation 스택, 로그 그룹 포함)",
    )

    parser.add_argument(
        "--stack-name",
        default=DEFAULT_STACK_NAME,
        help=f"CloudFormation 스택 이름 (기본값: {DEFAULT_STACK_NAME})",
    )

    args = parser.parse_args()

    # --all 사용 시 --keep-ecr, --keep-ssm 무시
    if args.delete_all and (args.keep_ecr or args.keep_ssm):
        logger.warning("--all 사용 시 --keep-ecr, --keep-ssm 옵션은 무시됩니다.")

    # 에이전트 정보 조회
    agent_info = get_agent_info(args.region)

    if not agent_info and not args.delete_all:
        logger.error("배포된 에이전트를 찾을 수 없음")
        sys.exit(1)

    agent_id = agent_info.get("agent_id")
    agent_arn = agent_info.get("agent_arn")
    ecr_uri = agent_info.get("ecr_uri")
    agent_name = agent_info.get("agent_name", DEFAULT_AGENT_NAME)

    # 확인
    if not args.force:
        print()
        print("=" * 60)
        if args.delete_all:
            print("경고: 모든 관련 리소스가 삭제됩니다:")
        else:
            print("경고: 다음 리소스가 삭제됩니다:")
        print("=" * 60)

        if args.delete_all:
            # --all: 모든 리소스 표시
            if agent_id:
                print(f"  Agent ID:  {agent_id}")
            if agent_arn:
                print(f"  Agent ARN: {agent_arn}")
            if ecr_uri:
                print(f"  ECR URI:   {ecr_uri}")
            print("  SSM 파라미터 (runtime_arn, runtime_id, runtime_iam_role)")
            print(f"  CodeBuild 프로젝트: bedrock-agentcore-{agent_name}-builder")
            print(f"  CodeBuild IAM 역할")
            print(f"  CodeBuild S3 소스 버킷")
            print(f"  Knowledge Base (datasets.yaml에 정의된 모든 KB + OpenSearch + S3)")
            print(f"  CloudWatch 로그 그룹 (/aws/bedrock-agentcore/runtimes/*)")
            print(f"  CloudFormation 스택: {args.stack_name}")
            print(f"  로컬 파일: .deployment_metadata.json, .bedrock_agentcore.yaml")
        else:
            # 기본: 선택적 리소스 표시
            print(f"  Agent ID:  {agent_id}")
            print(f"  Agent ARN: {agent_arn}")
            if not args.keep_ecr and ecr_uri:
                print(f"  ECR URI:   {ecr_uri}")
            if not args.keep_ssm:
                print("  SSM 파라미터 (runtime_arn, runtime_id)")

        print("=" * 60)
        print()

        confirm = input("계속하시겠습니까? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("취소됨.")
            sys.exit(0)

    if args.delete_all:
        _cleanup_all(agent_id, agent_name, ecr_uri, args.region, args.stack_name)
    else:
        _cleanup_default(agent_id, ecr_uri, args.region, args.keep_ssm, args.keep_ecr)

    print()
    print("=" * 60)
    print("정리 완료")
    print("=" * 60)
    print()

    if not args.delete_all:
        print("참고: IAM 역할을 삭제하려면 다음을 실행하세요:")
        print("  aws cloudformation delete-stack --stack-name OpsAgentInfraStack")
        print("  또는: uv run python scripts/cleanup.py --all")
        print()


def _cleanup_default(
    agent_id: str | None,
    ecr_uri: str | None,
    region: str,
    keep_ssm: bool,
    keep_ecr: bool,
) -> None:
    """기본 정리 (기존 동작 유지)."""
    # 에이전트 삭제
    if agent_id:
        delete_agent(agent_id, region)

    # SSM 파라미터 삭제
    if not keep_ssm:
        delete_ssm_parameters(region)

    # ECR 리포지토리 삭제
    if not keep_ecr:
        delete_ecr_repository(ecr_uri, region)

    # 로컬 메타데이터 삭제
    script_dir = Path(__file__).parent
    metadata_file = script_dir / ".deployment_metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()
        logger.info("로컬 메타데이터 파일 삭제")


def _cleanup_all(
    agent_id: str | None,
    agent_name: str,
    ecr_uri: str | None,
    region: str,
    stack_name: str,
) -> None:
    """모든 리소스 삭제 (--all)."""
    # 1. 에이전트 삭제
    if agent_id:
        delete_agent(agent_id, region)

    # 2. SSM 파라미터 삭제 (runtime_iam_role 포함)
    delete_ssm_parameters(region, include_iam_role=True)

    # 3. ECR 리포지토리 삭제
    delete_ecr_repository(ecr_uri, region)

    # 4. CodeBuild 리소스 삭제 (프로젝트 + IAM 역할 + S3 버킷)
    delete_codebuild_resources(agent_name, region)

    # 5. Knowledge Base 삭제 (datasets.yaml 기반)
    delete_knowledge_bases(region)

    # 6. CloudWatch 로그 그룹 삭제
    delete_log_groups(agent_id, region)

    # 7. CloudFormation 스택 삭제 (완료까지 대기)
    delete_cloudformation_stack(stack_name, region)

    # 8. 로컬 파일 삭제
    delete_local_files()


if __name__ == "__main__":
    main()
