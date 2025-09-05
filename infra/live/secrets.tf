# Build DATABASE_URL from RDS
locals {
  db_host = aws_db_instance.postgres.address
  db_url  = "postgresql://${var.db_username}:${random_password.db.result}@${local.db_host}:5432/${var.db_name}"
  redis_url = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
}

resource "aws_secretsmanager_secret" "django_secret_key" {
  name = "${local.name}/DJANGO_SECRET_KEY"
}

resource "random_password" "django_secret" {
  length  = 50
  special = true
}

resource "aws_secretsmanager_secret_version" "django_secret_key_v" {
  secret_id     = aws_secretsmanager_secret.django_secret_key.id
  secret_string = random_password.django_secret.result
}

resource "aws_secretsmanager_secret" "database_url" {
  name = "${local.name}/DATABASE_URL"
}
resource "aws_secretsmanager_secret_version" "database_url_v" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = local.db_url
}

resource "aws_secretsmanager_secret" "redis_url" {
  name = "${local.name}/REDIS_URL"
}
resource "aws_secretsmanager_secret_version" "redis_url_v" {
  secret_id     = aws_secretsmanager_secret.redis_url.id
  secret_string = local.redis_url
}

# External APIs / Modal tokens (create placeholder; rotate later)
resource "aws_secretsmanager_secret" "openai_api_key" { name = "${local.name}/OPENAI_API_KEY" }
resource "aws_secretsmanager_secret_version" "openai_api_key_v" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = "SET_ME"
}

resource "aws_secretsmanager_secret" "modal_token" { name = "${local.name}/MODAL_TOKEN" }
resource "aws_secretsmanager_secret_version" "modal_token_v" {
  secret_id     = aws_secretsmanager_secret.modal_token.id
  secret_string = "SET_ME"
}