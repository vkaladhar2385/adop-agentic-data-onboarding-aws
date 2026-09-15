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

  lambda_role_arn_by_key = var.iam_owner == "terraform" ? {
    for k, r in aws_iam_role.lambda_fn : k => r.arn
    } : {
    for k, r in data.aws_iam_role.lambda_fn : k => r.arn
  }

  # Lake Formation grants follow the catalog Lambda (write), not the verifier.
  lambda_catalog_role_arn = lookup(local.lambda_role_arn_by_key, "register_catalog", try(values(local.lambda_role_arn_by_key)[0], null))
  lambda_role_arn         = local.lambda_catalog_role_arn
  lambda_role_name        = var.iam_owner == "terraform" ? try(aws_iam_role.lambda_fn["register_catalog"].name, null) : try(data.aws_iam_role.lambda_fn["register_catalog"].name, null)

  sfn_role_arn  = try(aws_iam_role.sfn[0].arn, try(data.aws_iam_role.sfn[0].arn, null))
  sfn_role_name = try(aws_iam_role.sfn[0].name, try(data.aws_iam_role.sfn[0].name, null))

  scheduler_role_arn = try(aws_iam_role.scheduler[0].arn, try(data.aws_iam_role.scheduler[0].arn, null))

  sink_lambda_name = {
    redshift   = "register_redshift_spectrum"
    opensearch = "index_gold_to_opensearch"
    redis      = "cache_quality_scores"
  }

  sink_lambda_arns = [
    for s in var.enabled_sinks :
    "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.workload}_${local.sink_lambda_name[s]}"
  ]
}
