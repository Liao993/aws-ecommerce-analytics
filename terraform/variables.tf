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

variable "redshift_password" {
  description = "Redshift admin password"
  type        = string
  sensitive   = true
}

variable "ec2_key_pair_name" {
  description = "Name of the existing EC2 key pair in ca-central-1"
  type        = string
  default     = "olist-key"  # ← change if your key pair has a different name
}

variable "ec2_ami_id" {
  description = "Amazon Linux 2023 AMI ID for ca-central-1"
  type        = string
  # Find the current AMI: Console → EC2 → AMI Catalog → search 'Amazon Linux 2023'
  # Example (verify before use): ami-0c9bfc21ac5bf10eb
}

output "redshift_s3_role_arn" {
  value       = aws_iam_role.redshift_s3.arn
  description = "Attach this role to Redshift Serverless namespace for COPY access"
}