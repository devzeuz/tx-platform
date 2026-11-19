# ==============================================================================
# Input Variables (The knobs and dials passed into our infrastructure blueprint)
# ==============================================================================

variable "bucket_name" {
  description = "The unique name for the S3 digital storage locker"
  type        = string
}

variable "aws_region" {
  description = "The AWS data center region to create the storage bucket in"
  type        = string
  default     = "us-east-1"
}

variable "index_document" {
  description = "The default home page file served when visitors open the URL"
  type        = string
  default     = "index.html"
}

variable "error_document" {
  description = "The fallback page shown if a visitor requests a page that doesn't exist"
  type        = string
  default     = "error.html"
}

