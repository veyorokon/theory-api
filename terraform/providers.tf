# terraform/providers.tf
provider "digitalocean" {
  # Uses DIGITALOCEAN_TOKEN environment variable
  # Spaces uses SPACES_ACCESS_KEY_ID and SPACES_SECRET_ACCESS_KEY
}

locals {
  # terraform workspace → env
  env = terraform.workspace != "default" ? terraform.workspace : "staging"

  # Spaces bucket name
  bucket_name = "${var.project}-artifacts-${local.env}"

  # Artifacts prefix
  artifacts_prefix = trim(var.artifacts_prefix, "/") != "" ? "${trim(var.artifacts_prefix, "/")}/" : ""
}
