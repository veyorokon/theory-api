# terraform/outputs.tf
output "artifacts_bucket" {
  value       = aws_s3_bucket.artifacts.bucket
  description = "S3 bucket name for artifacts"
}

output "artifacts_region" {
  value       = var.aws_region
  description = "Region for the artifacts bucket"
}

output "artifacts_prefix" {
  value       = local.artifacts_prefix
  description = "Root prefix used for presigned keys"
}

# Only if created; mark secret as sensitive
output "signer_access_key_id" {
  value       = try(aws_iam_access_key.signer_key[0].id, null)
  description = "Access key ID for the presigning IAM user (dev only)"
  sensitive   = true
}

output "signer_secret_access_key" {
  value       = try(aws_iam_access_key.signer_key[0].secret, null)
  description = "Secret access key for the presigning IAM user (dev only)"
  sensitive   = true
}

output "signer_user_arn" {
  value       = try(aws_iam_user.signer[0].arn, null)
  description = "IAM user ARN for presigning (dev only)"
}
