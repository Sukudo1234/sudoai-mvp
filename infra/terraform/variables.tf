# Core Infrastructure Variables
variable "aws_region" {
  description = "Primary AWS region - ap-south-1 (Mumbai) for low latency"
  type        = string
  default     = "ap-south-1"
}

variable "aws_fallback_region" {
  description = "Fallback region for GPU capacity constraints"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "sudoai-mvp"
}

# S3 Configuration
variable "s3_multipart_part_size" {
  description = "S3 multipart upload part size in MB"
  type        = number
  default     = 64
}

variable "s3_transfer_acceleration" {
  description = "Enable S3 Transfer Acceleration"
  type        = bool
  default     = true
}

# Batch Configuration
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

variable "batch_spot_percentage" {
  description = "Percentage of Spot instances in Batch (0-100)"
  type        = number
  default     = 80
}

# Database Configuration
variable "db_min_capacity" {
  description = "RDS Serverless v2 minimum capacity (ACUs)"
  type        = number
  default     = 0.5
}

variable "db_max_capacity" {
  description = "RDS Serverless v2 maximum capacity (ACUs)"
  type        = number
  default     = 4
}

# SQS Configuration
variable "sqs_visibility_timeout" {
  description = "SQS message visibility timeout in seconds"
  type        = number
  default     = 900  # 15 minutes for long-running GPU jobs
}

variable "sqs_max_receive_count" {
  description = "Maximum receives before moving to DLQ"
  type        = number
  default     = 3
}

# GitHub OIDC Configuration
variable "github_org" {
  description = "GitHub organization name"
  type        = string
  default     = "Sukudo1234"
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "sudoai-mvp"
}

# Resource Tagging
variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "sudoai-mvp"
    ManagedBy   = "terraform"
    Environment = "prod"
  }
}