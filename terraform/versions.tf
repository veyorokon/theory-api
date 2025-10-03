# terraform/versions.tf
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Remote state: configure via `-backend-config=backend.hcl` when ready
  # backend "s3" {}  # Commented out for local dev - uses local state
}
