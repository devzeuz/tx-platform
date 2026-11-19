# ==============================================================================
# Outputs (The information handed back to the platform once setup completes)
# ==============================================================================

output "bucket_name" {
  description = "The exact name of the S3 storage bucket that was created"
  value       = aws_s3_bucket.website.id
}

output "website_url" {
  description = "The live public website link that anyone can open in their browser"
  value       = "http://${aws_s3_bucket_website_configuration.website_config.website_endpoint}"
}

output "bucket_arn" {
  description = "The unique cloud identifier (ARN) for the storage bucket"
  value       = aws_s3_bucket.website.arn
}

