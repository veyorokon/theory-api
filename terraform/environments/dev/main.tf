# terraform/environments/dev/main.tf
# Dev environment - only Spaces bucket for CI testing

terraform {
  required_version = ">= 1.0"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

provider "digitalocean" {
  # Uses DIGITALOCEAN_TOKEN environment variable
  # Spaces uses SPACES_ACCESS_KEY_ID and SPACES_SECRET_ACCESS_KEY
}

locals {
  env         = "dev"
  project     = var.project
  bucket_name = "${var.project}-artifacts-${local.env}"
}

resource "digitalocean_spaces_bucket" "artifacts" {
  name   = local.bucket_name
  region = var.spaces_region
  acl    = "private"

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    max_age_seconds = 3600
  }
}

resource "digitalocean_spaces_bucket_object" "keep" {
  region  = digitalocean_spaces_bucket.artifacts.region
  bucket  = digitalocean_spaces_bucket.artifacts.name
  key     = ".keep"
  content = "keep"
  acl     = "private"
}

output "spaces_bucket" {
  value       = digitalocean_spaces_bucket.artifacts.name
  description = "Spaces bucket name"
}

output "spaces_region" {
  value       = digitalocean_spaces_bucket.artifacts.region
  description = "Spaces region"
}

output "spaces_endpoint" {
  value       = "https://${var.spaces_region}.digitaloceanspaces.com"
  description = "Spaces endpoint URL"
}

output "spaces_bucket_endpoint" {
  value       = digitalocean_spaces_bucket.artifacts.bucket_domain_name
  description = "Spaces bucket domain name"
}
