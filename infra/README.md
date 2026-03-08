# SentinelTrader — AWS ECS Fargate Deployment

## Architecture Overview

| Template | Description |
|---|---|
| `cloudformation.yml` | **Plan B** — No ALB. Task gets a dynamic public IP. Simple, zero cost for ALB. |
| `cloudformation-production.yml` | **Production** — ALB + HTTPS + ACM certificate + Route 53. Stable URL, TLS. |

---

## Plan B Deployment (cloudformation.yml)

### Prerequisites

1. **AWS CLI** configured: `aws configure`
2. **Docker** running
3. **jq** installed: `brew install jq` or `apt install jq`
4. Your AWS account has permissions for: ECR, ECS, CloudFormation, EC2, IAM, CloudWatch Logs

### Steps

#### 1. Set environment variables

```bash
export AWS_REGION=us-east-1          # change to your preferred region
export TELEGRAM_BOT_TOKEN=<token>    # optional
export TELEGRAM_CHAT_ID=<chat_id>    # optional
```

#### 2. Run the deploy script

```bash
cd infra
bash deploy.sh
```

The script will:
1. Create the ECR repository (if it doesn't exist)
2. Build the Docker image (`--platform linux/amd64`)
3. Push the image to ECR
4. Deploy/update the CloudFormation stack
5. Print the public IP and access URL

#### 3. Access the app

```
http://<task-public-ip>:8000
```

> **Note:** The public IP is dynamic — it changes every time the ECS task restarts. For a stable address, see the Production setup below.

---

### Updating the app

Just re-run `deploy.sh`. It will build a new image, push it, and force a new task deployment.

To force a new deployment without code changes (e.g. to restart the task):

```bash
aws ecs update-service \
  --cluster sentinel-trader \
  --service sentinel-trader \
  --force-new-deployment \
  --region us-east-1
```

---

### Finding the current task IP manually

```bash
# 1. Get task ARN
TASK=$(aws ecs list-tasks \
  --cluster sentinel-trader \
  --service-name sentinel-trader \
  --query 'taskArns[0]' --output text)

# 2. Get ENI ID
ENI=$(aws ecs describe-tasks \
  --cluster sentinel-trader --tasks $TASK \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value | [0]' \
  --output text)

# 3. Get public IP
aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text
```

---

### Tear down

```bash
aws cloudformation delete-stack --stack-name sentinel-trader --region us-east-1
```

> **Warning:** This deletes the ECR repository and all images. Export images first if needed.

---

## Production Deployment (cloudformation-production.yml)

### Additional prerequisites

1. **A domain** with a Route 53 hosted zone
2. **An ACM certificate** for the domain (must be in the same region):

```bash
aws acm request-certificate \
  --domain-name trading.example.com \
  --validation-method DNS \
  --region us-east-1
```
Then add the CNAME validation record to Route 53 and wait for `ISSUED` status.

### Deploy

```bash
aws cloudformation deploy \
  --template-file infra/cloudformation-production.yml \
  --stack-name sentinel-trader-prod \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --parameter-overrides \
    ImageUri=<ecr-image-uri> \
    DomainName=trading.example.com \
    HostedZoneId=Z1PA6795UKMFR9 \
    AcmCertificateArn=arn:aws:acm:us-east-1:123456789:certificate/abc-123 \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN \
    TelegramChatId=$TELEGRAM_CHAT_ID
```

Access at: `https://trading.example.com`

---

## IB Gateway Note

The current deployment does **not** include IB Gateway as a sidecar container. The app starts and waits for IB at `127.0.0.1:<IB_PORT>` — connection will fail until you add IB Gateway.

**Next step:** Add `ghcr.io/gnzsnz/ib-gateway` as a second container in the ECS Task Definition, sharing the same `awsvpc` network namespace, so both containers share `localhost`.

---

## Cost Estimate (Plan B, us-east-1)

| Resource | Cost |
|---|---|
| ECS Fargate 0.25 vCPU / 512 MB, 24/7 | ~$11/month |
| ECR storage (< 1 GB) | ~$0.10/month |
| CloudWatch Logs (7-day retention) | ~$0.50/month |
| Data transfer | ~$0.09/GB |
| **Total** | **~$12/month** |

Production (with ALB) adds ~$18/month for the load balancer.
