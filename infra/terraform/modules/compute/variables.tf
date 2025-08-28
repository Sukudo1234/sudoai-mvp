variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for Batch compute environments"
  type        = list(string)
}

variable "batch_security_group_id" {
  description = "Security group ID for Batch compute environments"
  type        = string
}

variable "cpu_instance_types" {
  description = "Instance types for CPU compute environment"
  type        = list(string)
  default     = ["c7i.large", "c6i.large", "c5.large"]
}

variable "gpu_instance_types" {
  description = "Instance types for GPU compute environment"
  type        = list(string)
  default     = ["g5.xlarge"]
}

variable "spot_percentage" {
  description = "Percentage of Spot instances (0-100)"
  type        = number
  default     = 80
}

variable "ecr_repository_url" {
  description = "ECR repository URL for worker container images"
  type        = string
}

variable "s3_raw_bucket" {
  description = "S3 bucket name for raw uploads"
  type        = string
}

variable "s3_out_bucket" {
  description = "S3 bucket name for processed outputs"
  type        = string
}

variable "sqs_queue_url" {
  description = "SQS queue URL for job messages"
  type        = string
}

variable "sqs_queue_arn" {
  description = "SQS queue ARN for IAM policies"
  type        = string
}

variable "database_url" {
  description = "Database connection URL"
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}