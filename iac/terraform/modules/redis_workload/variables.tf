# Extension module: ElastiCache Redis as a low-latency cache for the latest
# quality-gate scores (e.g. a real-time ops dashboard that shouldn't have to
# query Athena on every page load). See docs/EXTENDING_TO_NEW_SERVICES.md.
#
# NOTE: unlike the Redshift/OpenSearch extensions, Redis has no public AWS API
# endpoint -- it is only reachable inside a VPC. This module uses the account's
# *default* VPC/subnets to avoid standing up new networking for a sandbox demo;
# a production rollout would use private subnets in an existing VPC instead.

variable "workload" {
  type        = string
  description = "Workload whose quality scores get cached, e.g. advisory_transactions."
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "data_lake_bucket" {
  type        = string
  description = "Base data-lake bucket (Lambda deployment package lives under lambda-artifacts/<workload>/)."
}

variable "node_type" {
  type    = string
  default = "cache.t3.micro"
}

variable "vpc_id" {
  type        = string
  default     = null
  description = "VPC to deploy Redis + the cache Lambda into. Null falls back to the account's default VPC -- but many sandbox/org accounts don't have one, so pass this explicitly (aws ec2 describe-vpcs) when that lookup would fail."
}

variable "tags" {
  type    = map(string)
  default = {}
}
