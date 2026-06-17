output "s3_bucket_name" {
  description = "Nombre del bucket S3 de datos (usar como S3_BUCKET_NAME en .env)"
  value       = aws_s3_bucket.data.bucket
}

output "s3_bucket_arn" {
  description = "ARN del bucket S3 de datos"
  value       = aws_s3_bucket.data.arn
}
