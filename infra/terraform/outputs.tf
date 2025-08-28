# Core Infrastructure Outputs
output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "aws_account_id" {
  description = "AWS account ID"
  value       = local.account_id
}

# Storage
output "s3_raw_bucket_name" {
  description = "S3 bucket for raw uploads"
  value       = module.storage.raw_bucket_name
}

output "s3_out_bucket_name" {
  description = "S3 bucket for processed outputs"
  value       = module.storage.out_bucket_name
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain"
  value       = module.storage.cloudfront_domain
}

# Database
output "database_url" {
  description = "Database connection URL (sensitive)"
  value       = module.database.connection_url
  sensitive   = true
}

output "database_endpoint" {
  description = "RDS cluster endpoint"
  value       = module.database.cluster_endpoint
}

# Messaging
output "sqs_queue_url" {
  description = "SQS queue URL for jobs"
  value       = module.messaging.queue_url
}

output "sqs_dlq_url" {
  description = "SQS dead letter queue URL"
  value       = module.messaging.dlq_url
}

# Compute
output "batch_cpu_queue" {
  description = "AWS Batch CPU job queue name"
  value       = module.compute.cpu_job_queue
}

output "batch_gpu_queue" {
  description = "AWS Batch GPU job queue name"  
  value       = module.compute.gpu_job_queue
}

output "batch_cpu_job_definition" {
  description = "AWS Batch CPU job definition ARN"
  value       = module.compute.cpu_job_definition_arn
}

output "batch_gpu_job_definition" {
  description = "AWS Batch GPU job definition ARN"
  value       = module.compute.gpu_job_definition_arn
}

# Container Registry
output "ecr_repository_url" {
  description = "ECR repository URL for worker images"
  value       = module.container_registry.repository_url
}

# IAM
output "github_oidc_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC"
  value       = module.iam.github_oidc_role_arn
}

output "batch_execution_role_arn" {
  description = "IAM role ARN for Batch job execution"
  value       = module.iam.batch_execution_role_arn
}

output "api_service_role_arn" {
  description = "IAM role ARN for API service"
  value       = module.iam.api_service_role_arn
}

# Environment Variables for Application
output "app_environment_vars" {
  description = "Environment variables for application deployment"
  value = {
    AWS_REGION           = var.aws_region
    AWS_ACCOUNT_ID       = local.account_id
    AWS_S3_BUCKET_RAW    = module.storage.raw_bucket_name
    AWS_S3_BUCKET_OUT    = module.storage.out_bucket_name
    AWS_SQS_QUEUE_URL    = module.messaging.queue_url
    AWS_BATCH_CPU_QUEUE  = module.compute.cpu_job_queue
    AWS_BATCH_GPU_QUEUE  = module.compute.gpu_job_queue
    AWS_ECR_REPO_WORKER  = module.container_registry.repository_url
    CLOUDFRONT_DOMAIN    = module.storage.cloudfront_domain
  }
}