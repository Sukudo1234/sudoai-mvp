output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "github_oidc_role_arn" {
  description = "ARN of the GitHub Actions IAM role"
  value       = aws_iam_role.github_actions.arn
}

output "api_service_role_arn" {
  description = "ARN of the API service IAM role"
  value       = aws_iam_role.api_service.arn
}

output "batch_execution_role_arn" {
  description = "ARN of the Batch execution IAM role"
  value       = aws_iam_role.batch_execution.arn
}