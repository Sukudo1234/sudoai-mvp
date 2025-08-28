# CloudWatch Monitoring and Alarms

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/ecs/${var.name_prefix}-api"
  retention_in_days = 14

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-api-logs"
  })
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/aws/ecs/${var.name_prefix}-frontend" 
  retention_in_days = 7

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-frontend-logs"
  })
}

# SNS Topic for Alerts (optional - can be enabled later)
resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-alerts"
  })
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfVisibleMessages", "QueueName", "${var.name_prefix}-jobs"],
            [".", "ApproximateNumberOfMessagesDelayed", ".", "."],
            [".", "ApproximateNumberOfMessagesNotVisible", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "SQS Queue Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Batch", "SubmittedJobs", "JobQueue", "${var.name_prefix}-cpu-queue"],
            [".", "RunnableJobs", ".", "."],
            [".", "RunningJobs", ".", "."],
            [".", "SubmittedJobs", "JobQueue", "${var.name_prefix}-gpu-queue"],
            [".", "RunnableJobs", ".", "."],
            [".", "RunningJobs", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "Batch Job Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/S3", "BucketSizeBytes", "BucketName", "${var.name_prefix}-raw-*", "StorageType", "StandardStorage"],
            [".", ".", "BucketName", "${var.name_prefix}-out-*", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "S3 Storage Usage"
          period  = 86400
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-dashboard"
  })
}

# Custom Metrics for Application Health
resource "aws_cloudwatch_log_metric_filter" "api_errors" {
  name           = "${var.name_prefix}-api-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "[timestamp, request_id, level=\"ERROR\", ...]"

  metric_transformation {
    name      = "APIErrors"
    namespace = "SudoAI/API"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "api_error_rate" {
  alarm_name          = "${var.name_prefix}-api-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "APIErrors"
  namespace           = "SudoAI/API"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "This metric monitors API error rate"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# RDS Monitoring
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors RDS CPU utilization"

  dimensions = {
    DBClusterIdentifier = "${var.name_prefix}-cluster"
  }

  tags = var.tags
}

data "aws_region" "current" {}