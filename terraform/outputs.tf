output "s3_bucket_name" {
  description = "Name of the S3 data lake bucket"
  value       = aws_s3_bucket.data_lake.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 data lake bucket"
  value       = aws_s3_bucket.data_lake.arn
}

output "admin_role_arn" {
  description = "ARN of the olist admin IAM role"
  value       = aws_iam_role.admin.arn
}

output "senior_de_role_arn" {
  description = "ARN of the senior data engineer IAM role"
  value       = aws_iam_role.senior_de.arn
}

output "ae_role_arn" {
  description = "ARN of the analytics engineer / dbt IAM role"
  value       = aws_iam_role.ae.arn
}

output "junior_de_role_arn" {
  description = "ARN of the junior data engineer IAM role"
  value       = aws_iam_role.junior_de.arn
}

output "readonly_role_arn" {
  description = "ARN of the read-only analyst / sales IAM role"
  value       = aws_iam_role.readonly.arn
}
