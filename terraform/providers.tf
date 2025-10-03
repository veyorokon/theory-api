# terraform/providers.tf
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = var.project
      Environment = local.env
      ManagedBy   = "terraform"
    }
  }
}

locals {
  # terraform workspace → env
  env = terraform.workspace != "default" ? terraform.workspace : "dev"

  # Bucket name — globally unique; keep it predictable.
  bucket_name = "${var.project}-artifacts-${local.env}"

  # Prefix where processors will write (no leading slash, trailing slash ok)
  artifacts_prefix = trim(var.artifacts_prefix, "/") != "" ? "${trim(var.artifacts_prefix, "/")}/" : ""
}
