variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "suffix" {
  description = "Random suffix for unique resource names"
  type        = string
}

variable "s3_transfer_acceleration" {
  description = "Enable S3 Transfer Acceleration"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}