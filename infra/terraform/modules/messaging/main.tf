# SQS Queues for Job Processing

# KMS Key for SQS encryption
resource "aws_kms_key" "sqs" {
  description             = "KMS key for SQS queue encryption"
  deletion_window_in_days = 7
  
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sqs-kms"
  })
}

resource "aws_kms_alias" "sqs" {
  name          = "alias/${var.name_prefix}-sqs"
  target_key_id = aws_kms_key.sqs.key_id
}

# Dead Letter Queue
resource "aws_sqs_queue" "dlq" {
  name                       = "${var.name_prefix}-jobs-dlq"
  message_retention_seconds  = 1209600  # 14 days
  kms_master_key_id         = aws_kms_key.sqs.id
  kms_data_key_reuse_period_seconds = 300

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-jobs-dlq"
    Type = "dead-letter-queue"
  })
}

# Main Job Queue
resource "aws_sqs_queue" "main" {
  name                       = "${var.name_prefix}-jobs"
  visibility_timeout_seconds = var.visibility_timeout
  message_retention_seconds  = 1209600  # 14 days
  max_message_size          = 262144   # 256 KB
  delay_seconds             = 0
  receive_wait_time_seconds = 20       # Long polling

  # Encryption
  kms_master_key_id                = aws_kms_key.sqs.id
  kms_data_key_reuse_period_seconds = 300

  # Dead letter queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-jobs"
    Type = "main-job-queue"
  })
}

# Redrive policy for DLQ (to requeue messages back to main queue)
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue",
    sourceQueueArns   = [aws_sqs_queue.main.arn]
  })
}

# CloudWatch Alarms for monitoring
resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "${var.name_prefix}-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "100"
  alarm_description   = "This metric monitors queue depth"
  alarm_actions       = [] # TODO: Add SNS topic for notifications

  dimensions = {
    QueueName = aws_sqs_queue.main.name
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.name_prefix}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "This metric monitors dead letter queue"
  alarm_actions       = [] # TODO: Add SNS topic for notifications

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  tags = var.tags
}