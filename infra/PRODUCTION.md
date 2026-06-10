# Production vs Dev Deployment

Two CloudFormation templates exist in this directory. Both have been deployed
and validated; neither stack is currently active — infrastructure was torn down
for cost discipline. Either template can be redeployed in under 20 minutes via
`aws cloudformation deploy` (allow 3 additional minutes for IB Gateway 2FA approval
on first login). This document explains what each does, why they differ, and what
it costs to run each one.

---

## Templates at a glance

| | `cloudformation.yml` | `production.yaml` |
|---|---|---|
| **Label** | Dev / cost-optimised | Production-grade |
| **Access** | `http://<dynamic-ip>:8000` | `https://your-domain.com` |
| **TLS** | None | ACM certificate, TLS 1.3 |
| **Load balancer** | None — task is internet-facing | ALB (internet-facing) |
| **AZs** | 1 | 2 (required by ALB) |
| **Task count** | Fixed at 1 | Auto-scaling: min 1 / max 3 |
| **Port exposure** | 8000 open to `0.0.0.0/0` | 8000 reachable from ALB only |
| **WAF** | No | Optional (managed rule groups) |
| **Stable URL** | No — IP changes on every restart | Yes — Route 53 A alias to ALB |
| **Container Insights** | No | Yes |
| **Log retention** | 7 days | 30 days |
| **Monthly cost** | ~€18 | ~€35–40 |

Both templates run the **same two containers** in the same ECS Task:

```
ECS Task
├── ib-gateway   (ghcr.io/gnzsnz/ib-gateway)   port 4002 (paper) / 4001 (live)
└── sentinel-trader  (your ECR image)            port 8000
         └── connects to IB at 127.0.0.1:4002
```

---

## Architecture diagrams

### Dev (`cloudformation.yml`)

```
Internet
    │
    │  HTTP :8000
    ▼
┌─────────────────────────────────────────────┐
│  ECS Task (dynamic public IP)                │
│  ┌──────────────┐   ┌──────────────────────┐ │
│  │ ib-gateway   │   │  sentinel-trader     │ │
│  │ port 4002    │◄──│  port 8000           │ │
│  └──────────────┘   └──────────────────────┘ │
└─────────────────────────────────────────────┘
         Single AZ, single subnet
```

### Production (`production.yaml`)

```
Internet
    │
    │  HTTPS :443  /  HTTP :80 → redirect
    ▼
┌───────────────────────────────────────────────────────────────┐
│  Application Load Balancer  (spans AZ-A and AZ-B)             │
│  ACM certificate · TLS 1.3 · HTTP→HTTPS redirect              │
│  Optional: WAF (OWASP CommonRuleSet + KnownBadInputs)         │
└───────────┬───────────────────────────┬───────────────────────┘
            │ target group              │
     ┌──────┴──────┐             ┌──────┴──────┐
     │   AZ-A      │             │   AZ-B      │
     │  ECS Task   │             │  ECS Task   │
     │ ┌─────────┐ │             │ ┌─────────┐ │
     │ │ib-gw    │ │             │ │ib-gw    │ │
     │ │:4002    │ │             │ │:4002    │ │
     │ ├─────────┤ │             │ ├─────────┤ │
     │ │sentinel │ │             │ │sentinel │ │
     │ │:8000    │ │             │ │:8000    │ │
     │ └─────────┘ │             │ └─────────┘ │
     └─────────────┘             └─────────────┘
         Auto-scaling: 1–3 tasks based on CPU
```

Route 53 A alias record → ALB DNS name → stable `https://your-domain.com`

---

## Cost breakdown

### Dev (`cloudformation.yml`)

| Resource | Spec | Cost/month |
|---|---|---|
| ECS Fargate | 0.5 vCPU / 1 GB, 24/7 | ~€14 |
| ECR storage | < 1 GB | ~€0.10 |
| CloudWatch Logs | 7-day retention | ~€0.50 |
| Data transfer | ~1 GB | ~€0.10 |
| **Total** | | **~€15–18** |

### Production

| Resource | Spec | Cost/month |
|---|---|---|
| ECS Fargate | 0.5 vCPU / 1 GB × 1 task, 24/7 | ~€14 |
| ALB | Fixed hourly + LCU | ~€18–22 |
| Route 53 | 1 hosted zone + queries | ~€1 |
| ACM certificate | Free | €0 |
| ECR storage | < 1 GB | ~€0.10 |
| CloudWatch Logs | 30-day retention | ~€1.50 |
| Data transfer | ~1 GB | ~€0.10 |
| WAF *(optional)* | Base + per-million requests | ~€5–10 |
| **Total (no WAF)** | | **~€35–40** |
| **Total (with WAF)** | | **~€40–50** |

> Costs based on eu-west-1 (Ireland) pricing as of 2026.
> The ALB alone accounts for ~half the production cost increase.

---

## Why the dev template was the right choice

This project is a **personal trading assistant** — one user, one IB account,
accessed from a known IP. The production features don't add value in this context:

- **No ALB needed** — there's no horizontal scaling requirement, and a single task
  with a dynamic IP is fine for personal use with bookmarked URLs.
- **No TLS needed** — the app serves no third-party users and handles no
  payment data. The IB connection is already encrypted end-to-end by IB's own
  protocol. Adding HTTPS would require owning a domain (~€10/year) and managing
  a hosted zone (~€12/year).
- **No WAF needed** — the only user is the owner.
- **No multi-AZ needed** — brief downtime from an AZ failure is acceptable for a
  personal tool. ECS service recovery handles container crashes already.

The cost differential between dev and production-with-WAF is €37/month — €444/year
for infrastructure that provides no additional utility for a single-user app. That
differential is the reason the dev template was chosen when the project was active.

---

## Deploying the production template

### Prerequisites

1. A domain with a Route 53 hosted zone
2. An ACM certificate (must be `ISSUED` before deploying):

   ```bash
   aws acm request-certificate \
     --domain-name trading.example.com \
     --validation-method DNS \
     --region eu-west-1
   ```

   Add the CNAME record it gives you to Route 53, then wait for status `ISSUED`.

3. Same AWS permissions as the dev deploy plus: `elasticloadbalancing:*`,
   `route53:*`, `application-autoscaling:*`, `wafv2:*` (if WAF enabled)

### Deploy command

```bash
aws cloudformation deploy \
  --template-file infra/production.yaml \
  --stack-name sentinel-trader-prod \
  --capabilities CAPABILITY_NAMED_IAM \
  --region eu-west-1 \
  --parameter-overrides \
    ImageUri=<YOUR_ACCOUNT_ID>.dkr.ecr.eu-west-1.amazonaws.com/sentinel-trader:latest \
    DomainName=trading.example.com \
    HostedZoneId=Z1PA6795UKMFR9 \
    AcmCertificateArn=arn:aws:acm:eu-west-1:<YOUR_ACCOUNT_ID>:certificate/abc-123 \
    TwsUserId=$TWS_USERID \
    TwsPassword=$TWS_PASSWORD \
    TradingMode=paper \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN \
    TelegramChatId=$TELEGRAM_CHAT_ID \
    EnableWAF=false
```

Access at: `https://trading.example.com`

### A note on scaling and IB Gateway

The auto-scaling configuration (min 1, max 3) is included for completeness.
In practice, **scaling above 1 task is not useful** with the current architecture:

- Each ECS Task contains one IB Gateway instance
- Each IB Gateway occupies one IB client ID
- A single IB account supports a limited number of simultaneous API connections
- Multiple tasks would need distinct `IbClientId` values and careful session management

For a single-account deployment, set `MaxCapacity=1`. ECS service recovery
(automatic task restart on crash) already provides the availability that matters.
