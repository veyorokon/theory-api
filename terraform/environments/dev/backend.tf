# terraform/environments/dev/backend.tf
# Remote state backend using DigitalOcean Spaces

terraform {
  backend "s3" {
    endpoints = {
      s3 = "https://nyc3.digitaloceanspaces.com"
    }
    bucket                      = "theory-terraform-state"
    key                         = "dev/terraform.tfstate"
    region                      = "us-east-1" # Required but unused for Spaces
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}
