output "raw_bucket_name" {
  description = "Name of the raw uploads S3 bucket"
  value       = aws_s3_bucket.raw.id
}

output "raw_bucket_arn" {
  description = "ARN of the raw uploads S3 bucket"
  value       = aws_s3_bucket.raw.arn
}

output "out_bucket_name" {
  description = "Name of the outputs S3 bucket"
  value       = aws_s3_bucket.out.id
}

output "out_bucket_arn" {
  description = "ARN of the outputs S3 bucket"
  value       = aws_s3_bucket.out.arn
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.out.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.out.id
}

output "kms_key_id" {
  description = "KMS key ID for S3 encryption"
  value       = aws_kms_key.s3.id
}

output "kms_key_arn" {
  description = "KMS key ARN for S3 encryption"
  value       = aws_kms_key.s3.arn
}