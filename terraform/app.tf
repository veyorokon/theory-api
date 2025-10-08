# terraform/app.tf
# DigitalOcean App Platform - Django application

resource "digitalocean_app" "django" {
  spec {
    name   = "${var.project}-${local.env}"
    region = var.region

    # Django service
    service {
      name               = "django"
      instance_count     = 1
      instance_size_slug = var.app_size

      # GitHub source
      github {
        repo           = "veyorokon/theory-api"
        branch         = local.env == "main" ? "main" : "staging"
        deploy_on_push = true
      }

      # Dockerfile build
      dockerfile_path = "Dockerfile"

      # Health check
      health_check {
        http_path             = "/health/"
        initial_delay_seconds = 60
        period_seconds        = 30
        timeout_seconds       = 5
        success_threshold     = 1
        failure_threshold     = 3
      }

      # HTTP port
      http_port = 8000

      # Environment variables
      env {
        key   = "DJANGO_SETTINGS_MODULE"
        value = "backend.settings.production"
        type  = "GENERAL"
      }

      env {
        key   = "ALLOWED_HOSTS"
        value = "*"
        type  = "GENERAL"
      }

      env {
        key   = "STORAGE_BACKEND"
        value = "s3"
        type  = "GENERAL"
      }

      env {
        key   = "ARTIFACTS_BUCKET"
        value = digitalocean_spaces_bucket.artifacts.name
        type  = "GENERAL"
      }

      env {
        key   = "ARTIFACTS_REGION"
        value = var.spaces_region
        type  = "GENERAL"
      }

      env {
        key   = "ARTIFACTS_ENDPOINT"
        value = "https://${var.spaces_region}.digitaloceanspaces.com"
        type  = "GENERAL"
      }

      env {
        key   = "MODAL_ENVIRONMENT"
        value = local.env
        type  = "GENERAL"
      }

      # Secrets - passed via TF_VAR_* environment variables
      env {
        key   = "DJANGO_SECRET_KEY"
        value = var.django_secret_key
        type  = "SECRET"
      }

      env {
        key   = "STORAGE_ACCESS_KEY"
        value = var.storage_access_key
        type  = "SECRET"
      }

      env {
        key   = "STORAGE_SECRET_KEY"
        value = var.storage_secret_key
        type  = "SECRET"
      }

      env {
        key   = "DATABASE_URL"
        value = "$${theory.DATABASE_URL}"
        type  = "GENERAL"
        scope = "RUN_TIME"
      }
    }

    # Link to database
    database {
      name         = digitalocean_database_db.main.name
      cluster_name = digitalocean_database_cluster.postgres.name
      engine       = "PG"
      production   = true
    }
  }
}
