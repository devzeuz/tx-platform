# ==============================================================================
# S3 Static Website Infrastructure Blueprint (Tech term: Terraform Configuration)
# ==============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ------------------------------------------------------------------------------
# 1. The Cloud Storage Locker (Tech term: S3 Bucket)
# A secure place on AWS servers to hold your website files (HTML, CSS, JS, images).
# ------------------------------------------------------------------------------
resource "aws_s3_bucket" "website" {
  bucket        = var.bucket_name
  force_destroy = true # Allows easy cleanup if you decide to delete the deployment later
}

# ------------------------------------------------------------------------------
# 2. Unlock Public Access for Web Visitors (Tech term: Public Access Block Settings)
# By default, cloud storage is completely locked down. We open the door just enough
# so web visitors can view your public HTML files.
# ------------------------------------------------------------------------------
resource "aws_s3_bucket_public_access_block" "public_access" {
  bucket = aws_s3_bucket.website.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# ------------------------------------------------------------------------------
# 3. Enable Website Server Mode (Tech term: Static Website Hosting)
# Tells AWS to behave like a web server: serve 'index.html' when someone visits.
# ------------------------------------------------------------------------------
resource "aws_s3_bucket_website_configuration" "website_config" {
  bucket = aws_s3_bucket.website.id

  index_document {
    suffix = var.index_document
  }

  error_document {
    key = var.error_document
  }
}

# ------------------------------------------------------------------------------
# 4. Read-Only Permission Card (Tech term: S3 Bucket Policy)
# A rule written in standard cloud policy format that says:
# "Allow anyone on the internet to read (s3:GetObject) files inside this bucket."
# ------------------------------------------------------------------------------
resource "aws_s3_bucket_policy" "allow_public_read" {
  bucket     = aws_s3_bucket.website.id
  depends_on = [aws_s3_bucket_public_access_block.public_access]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.website.arn}/*"
      }
    ]
  })
}

