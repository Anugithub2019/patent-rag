variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Cloud Run and Artifact Registry region."
  type        = string
  default     = "australia-southeast1"
}

variable "github_repository" {
  description = "GitHub repository in owner/name form. Matching is case-sensitive."
  type        = string
}

variable "artifact_repository_id" {
  description = "Artifact Registry repository ID."
  type        = string
  default     = "patent-rag"
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name deployed by GitHub Actions."
  type        = string
  default     = "patent-rag"
}

variable "hashtag_secret_id" {
  description = "Secret Manager secret containing the Hashtag API key."
  type        = string
  default     = "hashtag-api-key"
}
