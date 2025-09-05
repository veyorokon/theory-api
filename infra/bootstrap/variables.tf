variable "project" {
  description = "Project slug (used for naming)"
  type        = string
}
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}