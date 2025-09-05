output "alb_dns_name"      { value = aws_lb.app.dns_name }
output "rds_endpoint"      { value = aws_db_instance.postgres.address }
output "redis_endpoint"    { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "ecr_repo"          { value = aws_ecr_repository.web.repository_url }
output "cluster_name"      { value = aws_ecs_cluster.main.name }
output "static_bucket"     { value = aws_s3_bucket.static.bucket }
output "media_bucket"      { value = aws_s3_bucket.media.bucket }