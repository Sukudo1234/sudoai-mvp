variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "visibility_timeout" {
  description = "SQS message visibility timeout in seconds"
  type        = number
  default     = 900  # 15 minutes
}

variable "max_receive_count" {
  description = "Maximum number of receives before moving to DLQ"
  type        = number
  default     = 3
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}