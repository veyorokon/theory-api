# terraform/outputs.tf

# App Platform outputs
output "app_url" {
  value       = "https://${digitalocean_app.django.default_ingress}"
  description = "Django application URL"
}

output "app_id" {
  value       = digitalocean_app.django.id
  description = "App Platform app ID"
}

# Database outputs
output "database_host" {
  value       = digitalocean_database_cluster.postgres.host
  description = "Database host"
  sensitive   = true
}

output "database_port" {
  value       = digitalocean_database_cluster.postgres.port
  description = "Database port"
}

output "database_name" {
  value       = digitalocean_database_db.main.name
  description = "Database name"
}

output "database_user" {
  value       = digitalocean_database_cluster.postgres.user
  description = "Database username"
  sensitive   = true
}

output "database_password" {
  value       = digitalocean_database_cluster.postgres.password
  description = "Database password"
  sensitive   = true
}

output "database_uri" {
  value       = digitalocean_database_cluster.postgres.uri
  description = "Database connection URI"
  sensitive   = true
}

# Spaces outputs
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
