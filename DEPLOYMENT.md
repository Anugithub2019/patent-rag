# Google Cloud Run CI/CD

The application is deployed as one Node service that queries the existing
Hashtag knowledge graph. Deployment does not run the uploader or require Redis.
Terraform owns the Google infrastructure; GitHub Actions tests, builds, pushes,
and deploys the application on successful pushes to `main`.

## Prerequisites

- A billed Google Cloud project
- `gcloud` and Terraform 1.7 or newer
- Project IAM and service-management permissions
- This code in a GitHub repository

Authenticate and select the project:

```sh
gcloud auth application-default login
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

## 1. Bootstrap remote Terraform state

The state bucket is the sole bootstrap resource because Terraform needs it before
initialization. Its name must be globally unique.

```sh
gcloud services enable storage.googleapis.com
gcloud storage buckets create gs://YOUR_UNIQUE_TF_STATE_BUCKET \
  --location=australia-southeast1 \
  --uniform-bucket-level-access
gcloud storage buckets update gs://YOUR_UNIQUE_TF_STATE_BUCKET --versioning
```

Keep this bucket private and restrict it to infrastructure administrators.

## 2. Provision Google infrastructure

```sh
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

Edit the copied file with the project ID and exact GitHub `owner/repository`, then:

```sh
terraform -chdir=infra init \
  -backend-config="bucket=YOUR_UNIQUE_TF_STATE_BUCKET" \
  -backend-config="prefix=patent-rag"
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
```

Terraform creates the required APIs, Artifact Registry repository, separate
deployment/runtime identities and IAM, GitHub OIDC federation, and an empty
`hashtag-api-key` Secret Manager secret.

## 3. Add the secret value

Terraform deliberately does not manage the secret version: putting the API key
through Terraform would preserve it in state. Confirm `.env` contains exactly one
unquoted `HASHTAG_API_KEY=...` line, then send it directly to Secret Manager:

```sh
sed -n 's/^HASHTAG_API_KEY=//p' .env | \
  gcloud secrets versions add hashtag-api-key --data-file=-
```

The command does not print the key. Run it again to create a rotated version.

## 4. Configure GitHub Actions

```sh
terraform -chdir=infra output -json github_actions_variables
```

In **GitHub → Settings → Secrets and variables → Actions → Variables**, create
every variable shown in that output:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCP_ARTIFACT_REPOSITORY`
- `GCP_CLOUD_RUN_SERVICE`
- `GCP_HASHTAG_SECRET_ID`
- `GCP_RUNTIME_SERVICE_ACCOUNT`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOY_SERVICE_ACCOUNT`

No Google service-account key or Hashtag key is stored in GitHub. GitHub receives
short-lived Google credentials through Workload Identity Federation.

## 5. Deploy

Merge or push to `main`. The `Contract and architecture` workflow runs all tests,
builds the production container, pushes a commit-addressed image to Artifact
Registry, and deploys Cloud Run with `HASHTAG_API_KEY` sourced from Secret Manager.
The deployment step prints the URL. Verify it with:

```sh
curl "https://YOUR_CLOUD_RUN_URL/api/health"
```

## Tester-deployment constraints

The Node runtime stores async jobs in memory. CI therefore limits Cloud Run to one
instance and keeps CPU allocated so upstream queries continue after submission.
This uses instance-based billing and is not horizontally scalable. Configure a
Google Cloud budget and remove the service after testing.

The service is public, and each request can consume paid Hashtag API capacity.
Share the URL only with intended testers. Add authentication, rate limiting, and
shared job storage before a wider release.
