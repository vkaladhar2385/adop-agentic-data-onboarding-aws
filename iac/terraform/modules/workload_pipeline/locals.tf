# ARN/name resolution when MCP owns KMS or IAM (data sources) vs Terraform resources.

locals {
  zone_names = toset(["bronze", "silver", "gold"])

  zone_kms_arns = var.kms_owner == "terraform" ? [
    for z in local.zone_names : aws_kms_key.zone[z].arn
    ] : [
    for z in local.zone_names : data.aws_kms_key.zone[z].arn
  ]

  zone_kms_alias_map = var.kms_owner == "terraform" ? {
    for z, a in aws_kms_alias.zone : z => a.name
    } : {
    for z in local.zone_names : z => "alias/${var.workload}-${z}"
  }

  glue_role_arn  = var.iam_owner == "terraform" ? aws_iam_role.glue[0].arn : data.aws_iam_role.glue[0].arn
  glue_role_name = var.iam_owner == "terraform" ? aws_iam_role.glue[0].name : data.aws_iam_role.glue[0].name

  lambda_role_arn  = var.iam_owner == "terraform" ? aws_iam_role.lambda[0].arn : data.aws_iam_role.lambda[0].arn
  lambda_role_name = var.iam_owner == "terraform" ? aws_iam_role.lambda[0].name : data.aws_iam_role.lambda[0].name

  sfn_role_arn  = var.iam_owner == "terraform" ? aws_iam_role.sfn[0].arn : data.aws_iam_role.sfn[0].arn
  sfn_role_name = var.iam_owner == "terraform" ? aws_iam_role.sfn[0].name : data.aws_iam_role.sfn[0].name

  scheduler_role_arn = var.iam_owner == "terraform" ? aws_iam_role.scheduler[0].arn : data.aws_iam_role.scheduler[0].arn
}
