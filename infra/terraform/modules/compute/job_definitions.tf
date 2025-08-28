# Job Definitions for Batch

# IAM Role for Job Execution
resource "aws_iam_role" "job_execution" {
  name = "${var.name_prefix}-job-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-job-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "job_execution" {
  role       = aws_iam_role.job_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Job role for accessing AWS services from within jobs
resource "aws_iam_role" "job_role" {
  name = "${var.name_prefix}-job-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-job-role"
  })
}

resource "aws_iam_role_policy" "job_role_policy" {
  name = "${var.name_prefix}-job-role-policy"
  role = aws_iam_role.job_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject", 
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetObjectVersion"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_raw_bucket}",
          "arn:aws:s3:::${var.s3_raw_bucket}/*",
          "arn:aws:s3:::${var.s3_out_bucket}",
          "arn:aws:s3:::${var.s3_out_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage", 
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.sqs_queue_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# CPU Job Definition
resource "aws_batch_job_definition" "cpu" {
  name = "${var.name_prefix}-cpu-job-def"
  type = "container"

  platform_capabilities = ["EC2"]

  container_properties = jsonencode({
    image = "${var.ecr_repository_url}:latest"
    vcpus = 2
    memory = 4096
    
    jobRoleArn = aws_iam_role.job_role.arn
    executionRoleArn = aws_iam_role.job_execution.arn

    environment = [
      {
        name = "AWS_DEFAULT_REGION"
        value = data.aws_region.current.name
      },
      {
        name = "S3_RAW_BUCKET" 
        value = var.s3_raw_bucket
      },
      {
        name = "S3_OUT_BUCKET"
        value = var.s3_out_bucket
      },
      {
        name = "SQS_QUEUE_URL"
        value = var.sqs_queue_url
      },
      {
        name = "DATABASE_URL"
        value = var.database_url
      },
      {
        name = "JOB_TYPE"
        value = "cpu"
      }
    ]

    mountPoints = []
    volumes = []

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group = "/aws/batch/${var.name_prefix}"
        awslogs-region = data.aws_region.current.name
        awslogs-stream-prefix = "cpu"
      }
    }
  })

  retry_strategy {
    attempts = 3
  }

  timeout {
    attempt_duration_seconds = 3600  # 1 hour
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cpu-job-def"
    Type = "cpu"
  })
}

# GPU Job Definition
resource "aws_batch_job_definition" "gpu" {
  name = "${var.name_prefix}-gpu-job-def"
  type = "container"

  platform_capabilities = ["EC2"]

  container_properties = jsonencode({
    image = "${var.ecr_repository_url}:latest"
    vcpus = 4
    memory = 15360  # 15 GB for g5.xlarge
    
    jobRoleArn = aws_iam_role.job_role.arn
    executionRoleArn = aws_iam_role.job_execution.arn

    resourceRequirements = [
      {
        type = "GPU"
        value = "1"
      }
    ]

    environment = [
      {
        name = "AWS_DEFAULT_REGION"
        value = data.aws_region.current.name
      },
      {
        name = "S3_RAW_BUCKET"
        value = var.s3_raw_bucket
      },
      {
        name = "S3_OUT_BUCKET"
        value = var.s3_out_bucket
      },
      {
        name = "SQS_QUEUE_URL"
        value = var.sqs_queue_url
      },
      {
        name = "DATABASE_URL"
        value = var.database_url
      },
      {
        name = "JOB_TYPE"
        value = "gpu"
      },
      {
        name = "NVIDIA_VISIBLE_DEVICES"
        value = "all"
      }
    ]

    mountPoints = []
    volumes = []

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group = "/aws/batch/${var.name_prefix}"
        awslogs-region = data.aws_region.current.name
        awslogs-stream-prefix = "gpu"
      }
    }
  })

  retry_strategy {
    attempts = 2  # Fewer retries for GPU jobs (expensive)
  }

  timeout {
    attempt_duration_seconds = 7200  # 2 hours for GPU jobs
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-gpu-job-def"
    Type = "gpu"
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/batch/${var.name_prefix}"
  retention_in_days = 14

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-batch-logs"
  })
}

data "aws_region" "current" {}