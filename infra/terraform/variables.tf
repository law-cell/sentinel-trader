# Mirrors the Parameters block of ../cloudformation.yml.

variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Tag of the sentinel-trader image in the ECR repo created by ecr.tf"
}

variable "tws_userid" {
  type        = string
  description = "Interactive Brokers username (TWS_USERID)"
}

variable "tws_password" {
  type        = string
  sensitive   = true
  description = "Interactive Brokers password (TWS_PASSWORD)"
}

variable "trading_mode" {
  type        = string
  default     = "paper"
  description = "IB Gateway trading mode — paper (port 4002) or live (port 4001)"

  validation {
    condition     = contains(["paper", "live"], var.trading_mode)
    error_message = "trading_mode must be \"paper\" or \"live\"."
  }
}

variable "ib_client_id" {
  type    = number
  default = 1
}

variable "anthropic_api_key" {
  type        = string
  sensitive   = true
  description = "Anthropic API key for natural-language rule creation (Create with AI)"
}

variable "telegram_bot_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Telegram bot token for trade notifications (optional)"
}

variable "telegram_chat_id" {
  type        = string
  default     = ""
  description = "Telegram chat ID for trade notifications (optional)"
}
