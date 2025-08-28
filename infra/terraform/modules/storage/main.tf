# S3 Buckets and CloudFront Distribution

# KMS Key for S3 encryption
resource "aws_kms_key" "s3" {
  description             = "KMS key for S3 bucket encryption"
  deletion_window_in_days = 7
  
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-s3-kms"
  })
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.name_prefix}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

# S3 Bucket for Raw Uploads
resource "aws_s3_bucket" "raw" {
  bucket = "${var.name_prefix}-raw-${var.suffix}"
  
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-raw-bucket"
    Type = "raw-uploads"
  })
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_encryption" "raw" {
  bucket = aws_s3_bucket.raw.id

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        kms_master_key_id = aws_kms_key.s3.arn
        sse_algorithm     = "aws:kms"
      }
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "raw_lifecycle"
    status = "Enabled"

    # Delete incomplete multipart uploads after 7 days
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    # Transition to IA after 30 days, then Glacier after 90 days
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "POST", "PUT", "DELETE", "HEAD"]
    allowed_origins = ["*"] # TODO: Restrict to actual frontend domains
    expose_headers  = ["ETag", "Location"]
    max_age_seconds = 3000
  }
}

# S3 Transfer Acceleration
resource "aws_s3_bucket_accelerate_configuration" "raw" {
  count  = var.s3_transfer_acceleration ? 1 : 0
  bucket = aws_s3_bucket.raw.id
  status = "Enabled"
}

# S3 Bucket for Processed Outputs
resource "aws_s3_bucket" "out" {
  bucket = "${var.name_prefix}-out-${var.suffix}"
  
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-out-bucket"
    Type = "processed-outputs"
  })
}

resource "aws_s3_bucket_versioning" "out" {
  bucket = aws_s3_bucket.out.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_encryption" "out" {
  bucket = aws_s3_bucket.out.id

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        kms_master_key_id = aws_kms_key.s3.arn
        sse_algorithm     = "aws:kms"
      }
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "out" {
  bucket = aws_s3_bucket.out.id

  rule {
    id     = "out_lifecycle"
    status = "Enabled"

    # Transition to IA after 30 days
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

# CloudFront Distribution for fast downloads
resource "aws_cloudfront_origin_access_control" "out" {
  name                              = "${var.name_prefix}-out-oac"
  description                       = "OAC for output bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "out" {
  origin {
    domain_name              = aws_s3_bucket.out.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.out.id
    origin_id                = "S3-${aws_s3_bucket.out.id}"
  }

  enabled         = true
  is_ipv6_enabled = true
  comment         = "CloudFront distribution for processed outputs"

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.out.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cloudfront"
  })
}

# Bucket policy for CloudFront OAC
resource "aws_s3_bucket_policy" "out" {
  bucket = aws_s3_bucket.out.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.out.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.out.arn
          }
        }
      }
    ]
  })
}