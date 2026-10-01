# Remote state for CodeBuild factory provision. Config via backend.hcl at init time.
terraform {
  backend "s3" {}
}
