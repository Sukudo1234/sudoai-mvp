# IAM Roles and Policies

data "aws_caller_identity" "current" {}

# GitHub OIDC Provider
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]

  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd"
  ]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-github-oidc"
  })
}

# GitHub Actions Role
resource "aws_iam_role" "github_actions" {
  name = "${var.name_prefix}-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-github-actions-role"
  })
}

# GitHub Actions Policy
resource "aws_iam_role_policy" "github_actions" {
  name = "${var.name_prefix}-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ECR permissions
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:ListImages"
        ]
        Resource = [
          var.ecr_repository_arn,
          "arn:aws:ecr:*:${var.account_id}:repository/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      # Terraform state and deployment permissions
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.name_prefix}-terraform-state",
          "arn:aws:s3:::${var.name_prefix}-terraform-state/*"
        ]
      },
      # Limited infrastructure read permissions for Terraform
      {
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "batch:DescribeJobQueues",
          "batch:DescribeComputeEnvironments",
          "batch:DescribeJobDefinitions",
          "s3:GetBucketLocation",
          "s3:GetBucketVersioning",
          "sqs:GetQueueAttributes",
          "rds:DescribeDBClusters",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# API Service Role
resource "aws_iam_role" "api_service" {
  name = "${var.name_prefix}-api-service-role"

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
    Name = "${var.name_prefix}-api-service-role"
  })
}

resource "aws_iam_role_policy" "api_service" {
  name = "${var.name_prefix}-api-service-policy"
  role = aws_iam_role.api_service.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 permissions for multipart uploads and downloads
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject", 
          "s3:ListBucket",
          "s3:GetObjectVersion",
          "s3:CreateMultipartUpload",
          "s3:UploadPart",
          "s3:CompleteMultipartUpload",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
          "s3:ListMultipartUploads"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_raw_bucket}",
          "arn:aws:s3:::${var.s3_raw_bucket}/*",
          "arn:aws:s3:::${var.s3_out_bucket}",
          "arn:aws:s3:::${var.s3_out_bucket}/*"
        ]
      },
      # SQS permissions
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility",
          "sqs:PurgeQueue"
        ]
        Resource = [
          var.sqs_queue_arn,
          var.sqs_dlq_arn
        ]
      },
      # Batch permissions
      {
        Effect = "Allow"
        Action = [
          "batch:SubmitJob",
          "batch:DescribeJobs",
          "batch:TerminateJob",
          "batch:CancelJob",
          "batch:ListJobs"
        ]
        Resource = "*"
      },
      # CloudWatch Logs
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

# Batch Execution Role (referenced from compute module)
resource "aws_iam_role" "batch_execution" {
  name = "${var.name_prefix}-batch-execution-role"

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
    Name = "${var.name_prefix}-batch-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_execution" {
  role       = aws_iam_role.batch_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}