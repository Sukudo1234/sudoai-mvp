terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.common_tags
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# Random suffix for unique resource names
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  suffix     = random_id.suffix.hex
  
  # Resource naming
  name_prefix = "${var.project_name}-${var.environment}"
  
  # Common tags with computed values
  tags = merge(var.common_tags, {
    Region    = var.aws_region
    AccountId = local.account_id
  })
}

# Core Infrastructure Modules
module "networking" {
  source = "./modules/networking"
  
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "storage" {
  source = "./modules/storage"
  
  name_prefix                = local.name_prefix
  suffix                    = local.suffix
  s3_transfer_acceleration  = var.s3_transfer_acceleration
  tags                      = local.tags
}

module "database" {
  source = "./modules/database"
  
  name_prefix    = local.name_prefix
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids
  min_capacity   = var.db_min_capacity
  max_capacity   = var.db_max_capacity
  tags           = local.tags
}

module "messaging" {
  source = "./modules/messaging"
  
  name_prefix            = local.name_prefix
  visibility_timeout     = var.sqs_visibility_timeout
  max_receive_count      = var.sqs_max_receive_count
  tags                   = local.tags
}

module "compute" {
  source = "./modules/compute"
  
  name_prefix           = local.name_prefix
  vpc_id               = module.networking.vpc_id
  subnet_ids           = module.networking.private_subnet_ids
  cpu_instance_types   = var.cpu_instance_types
  gpu_instance_types   = var.gpu_instance_types
  spot_percentage      = var.batch_spot_percentage
  ecr_repository_url   = module.container_registry.repository_url
  s3_raw_bucket        = module.storage.raw_bucket_name
  s3_out_bucket        = module.storage.out_bucket_name
  sqs_queue_url        = module.messaging.queue_url
  database_url         = module.database.connection_url
  tags                 = local.tags
}

module "container_registry" {
  source = "./modules/ecr"
  
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "iam" {
  source = "./modules/iam"
  
  name_prefix        = local.name_prefix
  account_id         = local.account_id
  s3_raw_bucket      = module.storage.raw_bucket_name
  s3_out_bucket      = module.storage.out_bucket_name
  sqs_queue_arn      = module.messaging.queue_arn
  sqs_dlq_arn        = module.messaging.dlq_arn
  ecr_repository_arn = module.container_registry.repository_arn
  github_org         = var.github_org
  github_repo        = var.github_repo
  tags               = local.tags
}

module "monitoring" {
  source = "./modules/monitoring"
  
  name_prefix = local.name_prefix
  tags        = local.tags
}