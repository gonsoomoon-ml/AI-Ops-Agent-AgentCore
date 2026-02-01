#!/bin/bash
# =============================================================================
# OpsAgent AgentCore Infrastructure Deployment Script
# =============================================================================
#
# This script deploys the AWS infrastructure required for OpsAgent on AgentCore:
#   - IAM Role (RuntimeAgentCoreRole)
#   - SSM Parameters
#
# Usage:
#   ./agentcore/deploy_infra.sh [STACK_NAME]
#
# Examples:
#   ./agentcore/deploy_infra.sh                    # Default stack name
#   ./agentcore/deploy_infra.sh MyOpsAgentStack    # Custom stack name
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - IAM permissions: CloudFormation, IAM, SSM
#
# =============================================================================

set -e  # Exit on error

# ----- Script directory -----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ----- Configuration -----
STACK_NAME=${1:-OpsAgentInfraStack}
TEMPLATE_FILE="$SCRIPT_DIR/cloudformation/infrastructure.yaml"
REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "============================================="
echo "  OpsAgent Infrastructure Deployment"
echo "============================================="
echo "  Region:     $REGION"
echo "  Account:    $ACCOUNT_ID"
echo "  Stack:      $STACK_NAME"
echo "  Template:   $TEMPLATE_FILE"
echo "============================================="
echo ""

# ----- Validate template -----
echo "[1/3] Validating CloudFormation template..."
aws cloudformation validate-template \
  --template-body "file://$TEMPLATE_FILE" \
  --region "$REGION" > /dev/null
echo "      Template validation passed"
echo ""

# ----- Deploy stack -----
echo "[2/3] Deploying CloudFormation stack..."
echo "      This may take 1-2 minutes..."
echo ""

OUTPUT=$(aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$TEMPLATE_FILE" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --tags Application=OpsAgent Component=AgentCore 2>&1) || {

  if echo "$OUTPUT" | grep -q "No changes to deploy"; then
    echo "      No changes to deploy (stack already up to date)"
  else
    echo "      Deployment failed:"
    echo "$OUTPUT"
    exit 1
  fi
}

echo "      Stack deployment complete"
echo ""

# ----- Get outputs -----
echo "[3/3] Retrieving stack outputs..."

RUNTIME_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='RuntimeRoleArn'].OutputValue" \
  --output text \
  --region "$REGION")

echo ""
echo "============================================="
echo "  Deployment Complete!"
echo "============================================="
echo ""
echo "  Runtime IAM Role ARN:"
echo "    $RUNTIME_ROLE_ARN"
echo ""
echo "  SSM Parameter:"
echo "    /app/opsagent/agentcore/runtime_iam_role"
echo ""
echo "============================================="
echo "  Next Steps:"
echo "============================================="
echo ""
echo "  1. Deploy the AgentCore Runtime:"
echo "     cd agentcore"
echo "     uv run python scripts/deploy.py"
echo ""
echo "  2. Test the deployed agent:"
echo "     uv run python scripts/invoke.py --prompt 'Show me errors in payment-service'"
echo ""
echo "============================================="
