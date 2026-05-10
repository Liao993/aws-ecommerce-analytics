variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ca-central-1"
}

variable "bucket_name" {
  description = "S3 bucket name for the data lake"
  type        = string
  default     = "olist-ecommerce-tara888"
}

variable "project_name" {
  description = "Project prefix applied to all resource names and tags"
  type        = string
  default     = "olist"
}
