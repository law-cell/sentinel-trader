# SentinelTrader — AWS ECS Fargate Deployment

## Architecture Overview

| Template | Description |
|---|---|
| `cloudformation.yml` | **Plan B** — No ALB. Task gets a dynamic public IP. IB Gateway sidecar included. |
| `cloudformation-production.yml` | **Production** — ALB + HTTPS + ACM certificate + Route 53. Stable URL, TLS. |

### Container layout

Both templates run two containers in the same ECS Task (shared `awsvpc` network → shared `localhost`):

```
ECS Task
├── ib-gateway   (ghcr.io/gnzsnz/ib-gateway)  → port 4002 (paper) / 4001 (live)
└── sentinel-trader  (ECR image)               → port 8000
         └── connects to IB at 127.0.0.1:4002
```

---

## IB Gateway Configuration

### Credentials

Set these in `.env` or export them before running `deploy.sh`:

```bash
TWS_USERID=your_ib_username      # your IB account username
TWS_PASSWORD=your_ib_password    # your IB account password
TRADING_MODE=paper               # paper or live
```

### 2FA (Two-Factor Authentication)

IB accounts with 2FA enabled will pause at login waiting for the IBKR Mobile notification.

The `gnzsnz/ib-gateway` image handles this with two settings already configured:

| Variable | Value | Effect |
|---|---|---|
| `TWOFA_TIMEOUT_ACTION` | `restart` | Restarts IB Gateway on 2FA timeout instead of crashing |
| `RELOGIN_AFTER_TWOFA_TIMEOUT` | `yes` | Automatically retries login after restart |

**What you need to do:** Approve the IBKR Mobile push notification within ~3 minutes of each gateway start. After approval, the gateway stays connected until the daily auto-restart.

### Daily auto-restart

`AUTO_RESTART_TIME=11:59 PM` with `TIME_ZONE=Europe/Dublin` triggers a daily restart just before midnight Irish time. IB forces a brief disconnect around this time anyway — the restart ensures a clean reconnect. SentinelTrader's auto-reconnect logic handles the brief outage automatically.

---

## Plan B Deployment (cloudformation.yml)

### Prerequisites

1. **AWS CLI** configured: `aws configure`
2. **Docker** running
3. **jq** installed: `brew install jq` or `apt install jq`
4. IB credentials in `.env` or environment: `TWS_USERID`, `TWS_PASSWORD`
5. AWS permissions: ECR, ECS, CloudFormation, EC2, IAM, CloudWatch Logs

### Steps

#### 1. Set credentials

Edit `.env` in the project root:

```
TWS_USERID=your_ib_username
TWS_PASSWORD=your_ib_password
TRADING_MODE=paper
TELEGRAM_BOT_TOKEN=...   # optional
TELEGRAM_CHAT_ID=...     # optional
```

#### 2. Run the deploy script

```bash
export AWS_REGION=us-east-1
bash infra/deploy.sh
```

The script will:
1. Load credentials from `.env`
2. Create the ECR repository (if it doesn't exist)
3. Build the Docker image (`--platform linux/amd64`)
4. Push the image to ECR
5. Deploy/update the CloudFormation stack (with IB Gateway sidecar)
6. Print the public IP and access URL

#### 3. Approve 2FA on your phone

Within ~3 minutes of the task starting, approve the IBKR Mobile push notification. The gateway will then connect and SentinelTrader will show "IB Connected" in the top bar.

#### 4. Access the app

```
http://<task-public-ip>:8000
```

> **Note:** The public IP is dynamic — it changes every time the ECS task restarts. For a stable address, see the Production setup below.

---

### Updating the app

Just re-run `deploy.sh`. It rebuilds the image, pushes, and triggers a new task deployment.

To force a restart without code changes:

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
TASK=$(aws ecs list-tasks \
  --cluster sentinel-trader \
  --service-name sentinel-trader \
  --query 'taskArns[0]' --output text)

ENI=$(aws ecs describe-tasks \
  --cluster sentinel-trader --tasks $TASK \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value | [0]' \
  --output text)

aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text
```

---

### Viewing logs

```bash
# IB Gateway logs
aws logs tail /ecs/sentinel-trader --log-stream-name-prefix ib-gateway --follow

# App logs
aws logs tail /ecs/sentinel-trader --log-stream-name-prefix sentinel-trader --follow
```

---

### Tear down

```bash
aws cloudformation delete-stack --stack-name sentinel-trader --region us-east-1
```

The ECR repository is managed separately — delete it manually if needed:

```bash
aws ecr delete-repository --repository-name sentinel-trader --force --region us-east-1
```

---

## Local Testing with docker-compose

`docker-compose.yml` includes the IB Gateway service for local integration testing:

```bash
# Set credentials in .env first, then:
docker compose up --build
```

- IB Gateway starts on `localhost:4002` (paper)
- SentinelTrader connects to `ib-gateway:4002` (via Docker internal DNS)
- App accessible at `http://localhost:8000`

Approve the IBKR Mobile 2FA notification when prompted.

---

## Production Deployment (cloudformation-production.yml)

### Additional prerequisites

1. A domain with a Route 53 hosted zone
2. An ACM certificate for the domain:

```bash
aws acm request-certificate \
  --domain-name trading.example.com \
  --validation-method DNS \
  --region us-east-1
```

Add the CNAME validation record to Route 53 and wait for `ISSUED` status.

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
    TwsUserId=$TWS_USERID \
    TwsPassword=$TWS_PASSWORD \
    TradingMode=paper \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN \
    TelegramChatId=$TELEGRAM_CHAT_ID
```

Access at: `https://trading.example.com`

---

## Cost Estimate (Plan B, us-east-1)

| Resource | Cost |
|---|---|
| ECS Fargate 0.5 vCPU / 1 GB, 24/7 | ~$22/month |
| ECR storage (< 1 GB) | ~$0.10/month |
| CloudWatch Logs (7-day retention) | ~$0.50/month |
| Data transfer | ~$0.09/GB |
| **Total** | **~$23/month** |

Production (with ALB) adds ~$18/month for the load balancer.
