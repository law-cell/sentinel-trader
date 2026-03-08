#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy SentinelTrader to ECS Fargate (Plan B)
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - jq installed (brew install jq / apt install jq)
#
# Usage:
#   export AWS_REGION=us-east-1
#   export TELEGRAM_BOT_TOKEN=<token>
#   export TELEGRAM_CHAT_ID=<chat_id>
#   cd infra && bash deploy.sh

set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────────

AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="sentinel-trader"
ECR_REPO="sentinel-trader"
IMAGE_TAG="${IMAGE_TAG:-latest}"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ─── Helpers ──────────────────────────────────────────────────────────────────

info()    { echo ""; echo "==> $*"; }
success() { echo ""; echo "✓  $*"; }
die()     { echo ""; echo "✗  ERROR: $*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."
}

# ─── Preflight ────────────────────────────────────────────────────────────────

require aws
require docker
require jq

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"

echo ""
echo "================================================"
echo "  SentinelTrader — ECS Fargate Deploy"
echo "================================================"
echo "  Account : ${AWS_ACCOUNT_ID}"
echo "  Region  : ${AWS_REGION}"
echo "  Image   : ${IMAGE_URI}"
echo "================================================"

# ─── Step 1: Ensure ECR repository exists ─────────────────────────────────────

info "Step 1: Ensuring ECR repository exists..."

if aws ecr describe-repositories \
    --repository-names "${ECR_REPO}" \
    --region "${AWS_REGION}" \
    --output text >/dev/null 2>&1; then
  echo "  Repository already exists."
else
  aws ecr create-repository \
    --repository-name "${ECR_REPO}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --output text >/dev/null
  echo "  Created repository: ${ECR_REPO}"
fi

success "ECR repository ready."

# ─── Step 2: Build Docker image ───────────────────────────────────────────────

info "Step 2: Building Docker image (this may take a few minutes)..."

docker build \
  --platform linux/amd64 \
  -t "${ECR_REPO}:${IMAGE_TAG}" \
  "${PROJECT_ROOT}"

success "Docker image built."

# ─── Step 3: Push to ECR ──────────────────────────────────────────────────────

info "Step 3: Pushing image to ECR..."

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

docker tag "${ECR_REPO}:${IMAGE_TAG}" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

success "Image pushed: ${IMAGE_URI}"

# ─── Step 4: Deploy / update CloudFormation stack ─────────────────────────────

info "Step 4: Deploying CloudFormation stack '${STACK_NAME}'..."

aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation.yml" \
  --stack-name "${STACK_NAME}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides \
    ImageUri="${IMAGE_URI}" \
    TelegramBotToken="${TELEGRAM_BOT_TOKEN}" \
    TelegramChatId="${TELEGRAM_CHAT_ID}" \
  --no-fail-on-empty-changeset

success "Stack deployed."

# ─── Step 5: Get task public IP ───────────────────────────────────────────────

info "Step 5: Retrieving public IP of running task..."

# ECS may take a few seconds to start the task after stack update
echo "  Waiting for task to start..."
sleep 15

TASK_ARN=$(aws ecs list-tasks \
  --cluster "${STACK_NAME}" \
  --service-name "${STACK_NAME}" \
  --region "${AWS_REGION}" \
  --desired-status RUNNING \
  --query 'taskArns[0]' \
  --output text)

if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
  echo "  No running task found yet. Check the ECS console."
  echo "  Once running, get the IP with:"
  echo "    bash ${SCRIPT_DIR}/get-ip.sh"
  exit 0
fi

ENI_ID=$(aws ecs describe-tasks \
  --cluster "${STACK_NAME}" \
  --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value | [0]' \
  --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids "${ENI_ID}" \
  --region "${AWS_REGION}" \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text)

# ─── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "================================================"
echo "  Deployed successfully!"
echo ""
echo "  App URL : http://${PUBLIC_IP}:8000"
echo "  API     : http://${PUBLIC_IP}:8000/api/health"
echo "  Docs    : http://${PUBLIC_IP}:8000/docs"
echo ""
echo "  NOTE: The IP changes on every task restart."
echo "  Upgrade to cloudformation-production.yml"
echo "  for a stable HTTPS URL via ALB + Route 53."
echo "================================================"
echo ""
