# OpsAgent AgentCore Deployment

Amazon Bedrock AgentCore Runtime 배포를 위한 스크립트 및 설정 파일.

## 개요

이 폴더는 OpsAgent를 AWS Bedrock AgentCore Runtime에 배포하기 위한 파일들을 포함합니다.

```
agentcore/
├── cloudformation/
│   └── infrastructure.yaml    # IAM Role, SSM Parameters
├── runtime/
│   ├── entrypoint.py          # BedrockAgentCoreApp 진입점
│   └── requirements.txt       # Runtime 의존성
├── scripts/
│   ├── deploy.py              # 배포 스크립트
│   ├── invoke.py              # 호출 테스트
│   └── cleanup.py             # 정리 스크립트
├── deploy_infra.sh            # CloudFormation 배포
└── README.md
```

## 사전 요구사항

1. **AWS CLI 설정**
   ```bash
   aws configure
   ```

2. **Python 패키지 설치**
   ```bash
   pip install bedrock-agentcore-starter-toolkit boto3
   ```

3. **Docker 설치** (로컬 빌드 시)
   ```bash
   # Ubuntu
   sudo apt install docker.io
   ```

## 배포 단계

### Step 1: 인프라 배포 (IAM Role)

```bash
./agentcore/deploy_infra.sh
```

이 스크립트는 다음을 생성합니다:
- `OpsAgentBedrockAgentCoreRole-{region}`: AgentCore Runtime 실행 역할
- `/app/opsagent/agentcore/runtime_iam_role`: SSM Parameter

### Step 2: AgentCore Runtime 배포

```bash
cd agentcore
uv run python scripts/deploy.py
```

옵션:
- `--name`: 에이전트 이름 (기본: ops-ai-agent)
- `--region`: AWS 리전 (기본: us-east-1)
- `--auto-update`: 기존 에이전트 업데이트

배포 시간: 약 5-10분 (Docker 빌드 포함)

### Step 3: 테스트

```bash
# 단일 프롬프트
uv run python scripts/invoke.py --prompt "payment-service 에러 로그 보여줘"

# 대화형 모드
uv run python scripts/invoke.py --interactive

# 미리 정의된 테스트
uv run python scripts/invoke.py --test error
```

## 인증 방식

이 배포는 **IAM SigV4 인증**을 사용합니다 (Cognito 불필요):

- 배포 시 `authorizer_configuration` 없음 → IAM 기본 인증
- boto3가 자동으로 AWS 자격 증명 사용
- JWT 토큰 관리 불필요

```python
# invoke.py에서의 호출 방식
client = boto3.client("bedrock-agentcore")
response = client.invoke_agent_runtime(
    agentRuntimeArn=agent_arn,
    runtimeSessionId=session_id,
    payload=json.dumps({"prompt": prompt})
)
```

## 정리

```bash
# 에이전트 삭제
uv run python scripts/cleanup.py

# CloudFormation 스택 삭제 (IAM Role)
aws cloudformation delete-stack --stack-name OpsAgentInfraStack
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Account                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AgentCore Runtime                       │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │  entrypoint.py (BedrockAgentCoreApp)        │    │   │
│  │  │    └── OpsAgent                             │    │   │
│  │  │          ├── Graph Workflow                 │    │   │
│  │  │          ├── Evaluation                     │    │   │
│  │  │          └── Tools (CloudWatch, etc.)       │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  RuntimeAgentCoreRole (IAM)                          │   │
│  │    • Bedrock Model Invocation                        │   │
│  │    • CloudWatch Logs Query                           │   │
│  │    • X-Ray Tracing                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 트러블슈팅

### AccessDeniedException

IAM 권한 부족. CloudFormation 스택이 정상 배포되었는지 확인:
```bash
aws cloudformation describe-stacks --stack-name OpsAgentInfraStack
```

### ResourceNotFoundException

에이전트가 아직 준비되지 않음. 배포 완료까지 대기:
```bash
aws bedrock-agentcore list-agent-runtimes
```

### Docker 빌드 실패

Docker 데몬 실행 확인:
```bash
sudo systemctl start docker
```

## 참조

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [AgentCore Runtime Permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
- [amazon-bedrock-agentcore-samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
