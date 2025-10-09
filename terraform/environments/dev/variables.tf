# terraform/environments/dev/variables.tf

variable "project" {
  description = "Project name for resource naming"
  type        = string
  default     = "theory"
}

variable "spaces_region" {
  description = "DigitalOcean Spaces region"
  type        = string
  default     = "nyc3"
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}
