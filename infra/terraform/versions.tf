terraform {
  required_version = ">= 1.10" # needed for S3-native state locking (use_lockfile)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State bucket was created by hand (versioned, encrypted, public access blocked).
  # It is NOT managed by this config — never delete it.
  backend "s3" {
    bucket       = "sentinel-trader-tfstate-073356057418"
    key          = "sentinel-trader/terraform.tfstate"
    region       = "eu-west-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "sentinel-trader"
      ManagedBy = "terraform"
    }
  }
}
