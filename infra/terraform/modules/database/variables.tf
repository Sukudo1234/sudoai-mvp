variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where the database will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the database"
  type        = list(string)
}

variable "vpc_security_group_id" {
  description = "Security group ID for database access"
  type        = string
}

variable "min_capacity" {
  description = "Minimum serverless capacity (ACUs)"
  type        = number
  default     = 0.5
}

variable "max_capacity" {
  description = "Maximum serverless capacity (ACUs)"
  type        = number
  default     = 4
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot when destroying"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}