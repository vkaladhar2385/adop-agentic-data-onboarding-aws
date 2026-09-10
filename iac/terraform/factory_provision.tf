# Option B — no-laptop factory provision (Harness → Gateway → SFN → CodeBuild)
module "factory_provision" {
  source = "./modules/factory_provision"

  environment      = var.environment
  aws_region       = var.aws_region
  account_id       = var.account_id
  data_lake_bucket = var.data_lake_bucket
  tags             = var.tags
}
