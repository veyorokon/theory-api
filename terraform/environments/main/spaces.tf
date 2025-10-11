# terraform/spaces.tf
# DigitalOcean Spaces bucket for artifact storage (S3-compatible)

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

# Spaces access key for Django and Modal to access bucket
resource "digitalocean_spaces_bucket_object" "keep" {
  region  = digitalocean_spaces_bucket.artifacts.region
  bucket  = digitalocean_spaces_bucket.artifacts.name
  key     = ".keep"
  content = "keep"
  acl     = "private"
}
