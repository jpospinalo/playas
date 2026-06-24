output "alb_url" {
  description = "URL pública del Application Load Balancer"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_backend_url" {
  description = "URL del repositorio ECR del backend"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "URL del repositorio ECR del frontend"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  description = "Nombre del clúster ECS"
  value       = aws_ecs_cluster.main.name
}

output "aws_account_id" {
  description = "ID de la cuenta AWS"
  value       = data.aws_caller_identity.current.account_id
}
