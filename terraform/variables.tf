# terraform/variables.tf
variable "project" {
  description = "Project slug used for naming"
  type        = string
  default     = "theory"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "artifacts_prefix" {
  description = "Top-level S3 prefix for all artifacts (e.g., 'artifacts/')"
  type        = string
  default     = "artifacts/"
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
  default     = ["*"] # tighten later per app domain
}

variable "enable_lifecycle_expiration" {
  description = "Whether to enable object expiration (days)"
  type        = bool
  default     = false
}

variable "lifecycle_expiration_days" {
  description = "If enabled, days to retain objects"
  type        = number
  default     = 90
}

variable "create_signer_user" {
  description = "Create an IAM user for Django presigning (true for dev/CI; false if using OIDC/instance role)"
  type        = bool
  default     = true
}

variable "create_user_access_key" {
  description = "Create an access key for the signer IAM user (discouraged for long-term prod)"
  type        = bool
  default     = true
}
