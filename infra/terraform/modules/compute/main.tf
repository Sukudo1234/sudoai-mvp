# AWS Batch Compute Environments and Job Queues

# IAM Role for Batch Service
resource "aws_iam_role" "batch_service" {
  name = "${var.name_prefix}-batch-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "batch.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-batch-service-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_service" {
  role       = aws_iam_role.batch_service.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

# IAM Role for EC2 Instances in Batch
resource "aws_iam_role" "batch_instance" {
  name = "${var.name_prefix}-batch-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-batch-instance-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_instance_ecs" {
  role       = aws_iam_role.batch_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

# Custom policy for batch instances to access S3 and SQS
resource "aws_iam_role_policy" "batch_instance_custom" {
  name = "${var.name_prefix}-batch-instance-policy"
  role = aws_iam_role.batch_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
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
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage"
        ]
        Resource = var.sqs_queue_arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "batch_instance" {
  name = "${var.name_prefix}-batch-instance-profile"
  role = aws_iam_role.batch_instance.name

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-batch-instance-profile"
  })
}

# Launch Template for CPU Compute Environment
resource "aws_launch_template" "cpu" {
  name_prefix   = "${var.name_prefix}-cpu-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.cpu_instance_types[0]

  vpc_security_group_ids = [var.batch_security_group_id]
  
  iam_instance_profile {
    name = aws_iam_instance_profile.batch_instance.name
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    ecs_cluster_name = "${var.name_prefix}-cpu-cluster"
  }))

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.tags, {
      Name = "${var.name_prefix}-cpu-instance"
    })
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cpu-launch-template"
  })
}

# Launch Template for GPU Compute Environment  
resource "aws_launch_template" "gpu" {
  name_prefix   = "${var.name_prefix}-gpu-"
  image_id      = data.aws_ssm_parameter.ecs_gpu_ami.value
  instance_type = var.gpu_instance_types[0]

  vpc_security_group_ids = [var.batch_security_group_id]
  
  iam_instance_profile {
    name = aws_iam_instance_profile.batch_instance.name
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    ecs_cluster_name = "${var.name_prefix}-gpu-cluster"
  }))

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.tags, {
      Name = "${var.name_prefix}-gpu-instance"
    })
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-gpu-launch-template"
  })
}

# CPU Compute Environment
resource "aws_batch_compute_environment" "cpu" {
  compute_environment_name = "${var.name_prefix}-cpu-ce"
  type                    = "MANAGED"
  state                   = "ENABLED"
  service_role           = aws_iam_role.batch_service.arn

  compute_resources {
    type                = "EC2"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    
    min_vcpus     = 0
    max_vcpus     = 256
    desired_vcpus = 0

    instance_types = var.cpu_instance_types
    
    spot_iam_fleet_request_role = aws_iam_role.batch_spot_fleet.arn
    
    subnets         = var.subnet_ids
    security_group_ids = [var.batch_security_group_id]
    
    instance_role = aws_iam_instance_profile.batch_instance.arn
    
    launch_template {
      launch_template_id = aws_launch_template.cpu.id
      version           = "$Latest"
    }

    tags = merge(var.tags, {
      Name = "${var.name_prefix}-cpu-compute-env"
    })
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cpu-ce"
  })

  depends_on = [
    aws_iam_role_policy_attachment.batch_service
  ]
}

# GPU Compute Environment
resource "aws_batch_compute_environment" "gpu" {
  compute_environment_name = "${var.name_prefix}-gpu-ce"
  type                    = "MANAGED" 
  state                   = "ENABLED"
  service_role           = aws_iam_role.batch_service.arn

  compute_resources {
    type                = "EC2"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    
    min_vcpus     = 0
    max_vcpus     = 64
    desired_vcpus = 0

    instance_types = var.gpu_instance_types
    
    spot_iam_fleet_request_role = aws_iam_role.batch_spot_fleet.arn
    
    subnets         = var.subnet_ids
    security_group_ids = [var.batch_security_group_id]
    
    instance_role = aws_iam_instance_profile.batch_instance.arn
    
    launch_template {
      launch_template_id = aws_launch_template.gpu.id
      version           = "$Latest"
    }

    tags = merge(var.tags, {
      Name = "${var.name_prefix}-gpu-compute-env"
    })
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-gpu-ce"
  })

  depends_on = [
    aws_iam_role_policy_attachment.batch_service
  ]
}

# IAM Role for Spot Fleet
resource "aws_iam_role" "batch_spot_fleet" {
  name = "${var.name_prefix}-batch-spot-fleet-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "spotfleet.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-batch-spot-fleet-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_spot_fleet" {
  role       = aws_iam_role.batch_spot_fleet.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2SpotFleetTaggingRole"
}

# CPU Job Queue
resource "aws_batch_job_queue" "cpu" {
  name     = "${var.name_prefix}-cpu-queue"
  state    = "ENABLED"
  priority = 100

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.cpu.arn
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cpu-queue"
  })
}

# GPU Job Queue  
resource "aws_batch_job_queue" "gpu" {
  name     = "${var.name_prefix}-gpu-queue"
  state    = "ENABLED"
  priority = 200

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.gpu.arn
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-gpu-queue"
  })
}

# Data sources for AMIs
data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id"
}

data "aws_ssm_parameter" "ecs_gpu_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended/image_id"
}