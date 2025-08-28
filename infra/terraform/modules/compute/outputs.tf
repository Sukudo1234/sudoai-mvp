output "cpu_compute_environment_arn" {
  description = "ARN of the CPU compute environment"
  value       = aws_batch_compute_environment.cpu.arn
}

output "gpu_compute_environment_arn" {
  description = "ARN of the GPU compute environment"
  value       = aws_batch_compute_environment.gpu.arn
}

output "cpu_job_queue" {
  description = "Name of the CPU job queue"
  value       = aws_batch_job_queue.cpu.name
}

output "gpu_job_queue" {
  description = "Name of the GPU job queue"
  value       = aws_batch_job_queue.gpu.name
}

output "cpu_job_queue_arn" {
  description = "ARN of the CPU job queue"
  value       = aws_batch_job_queue.cpu.arn
}

output "gpu_job_queue_arn" {
  description = "ARN of the GPU job queue"
  value       = aws_batch_job_queue.gpu.arn
}

output "cpu_job_definition_arn" {
  description = "ARN of the CPU job definition"
  value       = aws_batch_job_definition.cpu.arn
}

output "gpu_job_definition_arn" {
  description = "ARN of the GPU job definition"
  value       = aws_batch_job_definition.gpu.arn
}

output "job_execution_role_arn" {
  description = "ARN of the job execution role"
  value       = aws_iam_role.job_execution.arn
}

output "job_role_arn" {
  description = "ARN of the job role"
  value       = aws_iam_role.job_role.arn
}

output "batch_service_role_arn" {
  description = "ARN of the batch service role"
  value       = aws_iam_role.batch_service.arn
}