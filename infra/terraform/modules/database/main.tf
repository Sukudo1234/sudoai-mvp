# RDS Serverless v2 PostgreSQL Database

# Random password for database
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-subnet-group"
  })
}

# RDS Cluster Parameter Group for PostgreSQL 15
resource "aws_rds_cluster_parameter_group" "main" {
  family      = "aurora-postgresql15"
  name        = "${var.name_prefix}-cluster-pg"
  description = "Cluster parameter group for ${var.name_prefix}"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cluster-parameter-group"
  })
}

# RDS Aurora Serverless v2 Cluster
resource "aws_rds_cluster" "main" {
  cluster_identifier     = "${var.name_prefix}-cluster"
  engine                = "aurora-postgresql"
  engine_mode           = "provisioned"
  engine_version        = "15.4"
  database_name         = "sudoai"
  master_username       = "postgres"
  master_password       = random_password.db_password.result
  
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.main.name
  db_subnet_group_name           = aws_db_subnet_group.main.name
  vpc_security_group_ids         = [var.vpc_security_group_id]

  # Serverless v2 scaling configuration
  serverlessv2_scaling_configuration {
    max_capacity = var.max_capacity
    min_capacity = var.min_capacity
  }

  # Backup configuration
  backup_retention_period = 7
  preferred_backup_window = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"

  # Security
  storage_encrypted = true
  skip_final_snapshot = var.skip_final_snapshot

  # Enable logging
  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-cluster"
  })

  lifecycle {
    ignore_changes = [master_password]
  }
}

# RDS Cluster Instance (Serverless v2)
resource "aws_rds_cluster_instance" "main" {
  identifier     = "${var.name_prefix}-instance-1"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class = "db.serverless"
  engine         = aws_rds_cluster.main.engine
  engine_version = aws_rds_cluster.main.engine_version

  publicly_accessible = false
  
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-instance-1"
  })
}

# Secrets Manager secret for database credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.name_prefix}-db-credentials"
  description = "Database credentials for ${var.name_prefix}"

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_rds_cluster.main.master_username
    password = random_password.db_password.result
    engine   = "postgres"
    host     = aws_rds_cluster.main.endpoint
    port     = aws_rds_cluster.main.port
    dbname   = aws_rds_cluster.main.database_name
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}