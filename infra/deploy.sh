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

AWS_REGION="${AWS_REGION:-eu-west-1}"
STACK_NAME="sentinel-trader"
ECR_REPO="sentinel-trader"
IMAGE_TAG="${IMAGE_TAG:-latest}"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
TWS_USERID="${TWS_USERID:-}"
TWS_PASSWORD="${TWS_PASSWORD:-}"
TRADING_MODE="${TRADING_MODE:-paper}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env from project root (only fills vars not already set in environment)
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    # Skip blank lines and comments
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    # Must contain '='
    [[ "${line}" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    # Skip keys with spaces or special chars (invalid variable names)
    [[ "${key}" =~ [^a-zA-Z0-9_] ]] && continue
    # Strip inline comments and surrounding quotes
    value="${value%%#*}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value#\"}" ; value="${value%\"}"
    value="${value#\'}" ; value="${value%\'}"
    # Only export if the variable is currently empty
    eval "cur=\${${key}:-}"
    [[ -z "${cur}" ]] && export "${key}=${value}"
  done < "${ENV_FILE}"
fi

# Re-read after .env load
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
TWS_USERID="${TWS_USERID:-}"
TWS_PASSWORD="${TWS_PASSWORD:-}"
TRADING_MODE="${TRADING_MODE:-paper}"

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
echo "  Account      : ${AWS_ACCOUNT_ID}"
echo "  Region       : ${AWS_REGION}"
echo "  Image        : ${IMAGE_URI}"
echo "  Trading mode : ${TRADING_MODE}"
echo "  TWS user     : ${TWS_USERID:-<not set>}"
echo "================================================"

[[ -z "${TWS_USERID}" ]] && die "TWS_USERID is not set. Add it to .env or export it."
[[ -z "${TWS_PASSWORD}" ]] && die "TWS_PASSWORD is not set. Add it to .env or export it."

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

# cygpath converts MSYS /c/... paths to Windows C:\... for Docker on Windows
DOCKER_CONTEXT="$(cygpath -w "${PROJECT_ROOT}" 2>/dev/null || echo "${PROJECT_ROOT}")"
docker build \
  --platform linux/amd64 \
  -t "${ECR_REPO}:${IMAGE_TAG}" \
  "${DOCKER_CONTEXT}"

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

CFN_TEMPLATE="$(cygpath -w "${SCRIPT_DIR}/cloudformation.yml" 2>/dev/null || echo "${SCRIPT_DIR}/cloudformation.yml")"
aws cloudformation deploy \
  --template-file "${CFN_TEMPLATE}" \
  --stack-name "${STACK_NAME}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides \
    ImageUri="${IMAGE_URI}" \
    TelegramBotToken="${TELEGRAM_BOT_TOKEN}" \
    TelegramChatId="${TELEGRAM_CHAT_ID}" \
    TwsUserId="${TWS_USERID}" \
    TwsPassword="${TWS_PASSWORD}" \
    TradingMode="${TRADING_MODE}" \
    IbPort="$([ "${TRADING_MODE}" = "live" ] && echo 4001 || echo 4002)" \
  --no-fail-on-empty-changeset

success "Stack deployed."

# Force ECS to pull the latest image even if CloudFormation had no infra changes
aws ecs update-service \
  --cluster "${STACK_NAME}" \
  --service "${STACK_NAME}" \
  --force-new-deployment \
  --region "${AWS_REGION}" \
  --output text >/dev/null

# ─── Step 5: Get task public IP ───────────────────────────────────────────────

info "Step 5: Retrieving public IP of running task..."

# ECS may take a few seconds to start the task after force-new-deployment
echo "  Waiting for task to start..."
sleep 45

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
