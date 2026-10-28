# In the CloudFormation flow deploy.sh creates this repo with the CLI.
# Here Terraform owns it; deploy.sh still works against it because it
# skips creation when the repo already exists.

resource "aws_ecr_repository" "app" {
  name                 = "sentinel-trader"
  image_tag_mutability = "MUTABLE" # deploy.sh re-pushes :latest

  image_scanning_configuration {
    scan_on_push = true
  }
}
