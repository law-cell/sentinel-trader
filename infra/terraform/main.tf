# Terraform port of ../cloudformation.yml (Plan B: no ALB, dynamic public IP).
# Resource names match the CloudFormation stack on purpose — deploy with ONE
# of the two at a time, never both in the same account/region.

locals {
  name      = "sentinel-trader"
  ib_port   = var.trading_mode == "live" ? 4001 : 4002
  image_uri = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ── Networking ────────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "${local.name}-public-subnet" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-public-rt" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Security Group ────────────────────────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${local.name}-sg"
  description = "Allow inbound port 8000 for SentinelTrader"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP access to FastAPI"
  ip_protocol       = "tcp"
  from_port         = 8000
  to_port           = 8000
  cidr_ipv4         = "0.0.0.0/0"
}

# CloudFormation adds allow-all egress implicitly; Terraform does not.
# Without this the task cannot pull images or reach IB.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── IAM ───────────────────────────────────────────────────────────────────────

# ECS needs this role to pull images from ECR and write logs to CloudWatch
resource "aws_iam_role" "task_execution" {
  name = "${local.name}-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── CloudWatch Logs ───────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

# ── ECS ───────────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = local.name
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  cpu                      = "512"  # 0.5 vCPU — IB Gateway needs more than 0.25
  memory                   = "1024" # 1 GB
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([
    # ── IB Gateway sidecar ──
    # Both containers share the awsvpc network namespace → localhost.
    {
      name      = "ib-gateway"
      image     = "ghcr.io/gnzsnz/ib-gateway:latest"
      essential = true
      portMappings = [
        { containerPort = 4001, protocol = "tcp" }, # live
        { containerPort = 4002, protocol = "tcp" }, # paper
      ]
      environment = [
        { name = "TWS_USERID", value = var.tws_userid },
        { name = "TWS_PASSWORD", value = var.tws_password },
        { name = "TRADING_MODE", value = var.trading_mode },
        # Gateway defaults to a read-only API, which rejects order placement
        { name = "READ_ONLY_API", value = "no" },
        # On 2FA timeout: restart IB Gateway instead of exiting
        { name = "TWOFA_TIMEOUT_ACTION", value = "restart" },
        { name = "RELOGIN_AFTER_TWOFA_TIMEOUT", value = "yes" },
        # Auto-dismiss "Existing session detected" dialog (take over as primary)
        { name = "EXISTING_SESSION_DETECTED_ACTION", value = "primary" },
        # Daily auto-restart just before market open (avoids mid-session drops)
        { name = "AUTO_RESTART_TIME", value = "11:59 PM" },
        { name = "TIME_ZONE", value = "Europe/Dublin" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ib-gateway"
        }
      }
    },
    # ── SentinelTrader app ──
    {
      name      = local.name
      image     = local.image_uri
      essential = true
      # Wait for IB Gateway to start before the app tries to connect
      dependsOn    = [{ containerName = "ib-gateway", condition = "START" }]
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        # Same Task = shared localhost network namespace
        { name = "IB_HOST", value = "127.0.0.1" },
        { name = "IB_PORT", value = tostring(local.ib_port) },
        { name = "IB_CLIENT_ID", value = tostring(var.ib_client_id) },
        { name = "ANTHROPIC_API_KEY", value = var.anthropic_api_key },
        { name = "TELEGRAM_BOT_TOKEN", value = var.telegram_bot_token },
        { name = "TELEGRAM_CHAT_ID", value = var.telegram_chat_id },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = local.name
        }
      }
    },
  ])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    # Fargate assigns a dynamic public IP to the task ENI
    assign_public_ip = true
    subnets          = [aws_subnet.public.id]
    security_groups  = [aws_security_group.app.id]
  }

  # Service needs the subnet route to the IGW to pull ECR images
  depends_on = [aws_route.public_internet, aws_route_table_association.public]
}
