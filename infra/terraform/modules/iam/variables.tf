variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "s3_raw_bucket" {
  description = "S3 raw bucket name"
  type        = string
}

variable "s3_out_bucket" {
  description = "S3 output bucket name"
  type        = string
}

variable "sqs_queue_arn" {
  description = "SQS queue ARN"
  type        = string
}

variable "sqs_dlq_arn" {
  description = "SQS dead letter queue ARN"
  type        = string
}

variable "ecr_repository_arn" {
  description = "ECR repository ARN"
  type        = string
}

variable "github_org" {
  description = "GitHub organization name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name" 
  type        = string
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}