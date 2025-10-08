# terraform/database.tf
# Managed PostgreSQL database

resource "digitalocean_database_cluster" "postgres" {
  name       = "${var.project}-db-${local.env}"
  engine     = "pg"
  version    = "16"
  size       = var.db_size
  region     = var.region
  node_count = 1

  tags = ["${var.project}", local.env]
}

resource "digitalocean_database_db" "main" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = var.project
}
