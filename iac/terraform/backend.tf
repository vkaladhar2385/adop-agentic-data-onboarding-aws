# Remote state for CodeBuild factory provision (init with backend.hcl or -backend-config).
# Local / CI: terraform init -backend=false  OR  terraform init -backend-config=backend.hcl
terraform {
  backend "s3" {}
}
