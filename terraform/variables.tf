# terraform/variables.tf
variable "project" {
  description = "Project name for resource naming"
  type        = string
  default     = "theory"
}

variable "do_team" {
  description = "DigitalOcean team name"
  type        = string
  default     = "theory"
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "spaces_region" {
  description = "DigitalOcean Spaces region"
  type        = string
  default     = "nyc3"
}

variable "artifacts_prefix" {
  description = "Top-level prefix for artifacts in Spaces"
  type        = string
  default     = "artifacts/"
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

variable "db_size" {
  description = "Database cluster size slug"
  type        = string
  default     = "db-s-1vcpu-1gb" # $15/mo
}

variable "app_size" {
  description = "App Platform instance size"
  type        = string
  default     = "professional-xs" # $12/mo - 1GB RAM
}

variable "django_secret_key" {
  description = "Django SECRET_KEY"
  type        = string
  sensitive   = true
}

variable "storage_access_key" {
  description = "Storage access key (DO Spaces key)"
  type        = string
  sensitive   = true
}

variable "storage_secret_key" {
  description = "Storage secret key (DO Spaces secret)"
  type        = string
  sensitive   = true
}
