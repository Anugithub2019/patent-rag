output "github_actions_variables" {
  description = "Values to add as GitHub Actions repository variables."
  value = {
    GCP_PROJECT_ID                 = var.project_id
    GCP_REGION                     = var.region
    GCP_ARTIFACT_REPOSITORY        = google_artifact_registry_repository.application.repository_id
    GCP_CLOUD_RUN_SERVICE          = var.cloud_run_service_name
    GCP_HASHTAG_SECRET_ID          = google_secret_manager_secret.hashtag_api_key.secret_id
    GCP_RUNTIME_SERVICE_ACCOUNT    = google_service_account.runtime.email
    GCP_WORKLOAD_IDENTITY_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOY_SERVICE_ACCOUNT     = google_service_account.deployer.email
  }
}
