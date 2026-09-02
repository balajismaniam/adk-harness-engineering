#!/usr/bin/env bash
# deploy_sandbox_service.sh
# Automates deploying the Cloud Run Sandbox HTTP REST Service to Google Cloud Run.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================="
echo "Deploying ADK Agent to Google Cloud Run Service with --sandbox-launcher"
echo "================================================================="

# 1. Load and validate environment variables
if [ -f "$REPO_ROOT/.env" ]; then
    source "$REPO_ROOT/.env"
elif [ -f ".env" ]; then
    source ".env"
fi

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
CLOUD_RUN_REGION="${CLOUD_RUN_REGION:-us-west1}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
SA_NAME="${SA_NAME:-adk-runner-sa}"
SERVICE_NAME="adk-sandbox-service"

if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "  [ERROR] GOOGLE_CLOUD_PROJECT environment variable is not set."
    echo "          Please set it in your .env file or export GOOGLE_CLOUD_PROJECT='your-project-id'."
    exit 1
fi

echo "  [INFO] Project:          $GOOGLE_CLOUD_PROJECT"
echo "  [INFO] Region:           $CLOUD_RUN_REGION"
echo "  [INFO] AI Loc:           $GOOGLE_CLOUD_LOCATION"
echo "  [INFO] Service Account:  $SA_NAME"
echo "  [INFO] Service Name:     $SERVICE_NAME"

# 2. Enable required Google Cloud Service APIs
echo "  [INFO] Checking and enabling required Google Cloud APIs..."
SERVICES=(
    "run.googleapis.com"
    "cloudbuild.googleapis.com"
    "aiplatform.googleapis.com"
    "iam.googleapis.com"
)
for service in "${SERVICES[@]}"; do
    if ! gcloud services list --enabled --project="$GOOGLE_CLOUD_PROJECT" --filter="config.name:$service" --format="value(config.name)" | grep -q "$service"; then
        echo "         Enabling $service..."
        gcloud services enable "$service" --project="$GOOGLE_CLOUD_PROJECT"
    fi
done

# 3. Setup IAM Service Account
echo "  [INFO] Checking Service Account..."
SA_EMAIL="$SA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$GOOGLE_CLOUD_PROJECT" &>/dev/null; then
    echo "         Creating service account $SA_EMAIL..."
    gcloud iam service-accounts create "$SA_NAME" \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --description="ADK Sandbox Runner Service Account" \
        --display-name="ADK Sandbox Runner Service Account"
fi

echo "  [INFO] Granting required IAM roles..."
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/aiplatform.user" \
    --quiet &>/dev/null

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter" \
    --quiet &>/dev/null

# 4. Deploy Cloud Run Service Directly from Source with Sandbox Launcher
echo "  [INFO] Deploying Cloud Run Service '$SERVICE_NAME' directly from source with --sandbox-launcher..."
gcloud beta run deploy "$SERVICE_NAME" \
    --project="$GOOGLE_CLOUD_PROJECT" \
    --region="$CLOUD_RUN_REGION" \
    --source="$SCRIPT_DIR" \
    --service-account="$SA_EMAIL" \
    --sandbox-launcher \
    --no-cpu-throttling \
    --set-env-vars PYTHONUNBUFFERED="1",GOOGLE_GENAI_USE_ENTERPRISE="true",GOOGLE_CLOUD_LOCATION="$GOOGLE_CLOUD_LOCATION",GOOGLE_CLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT" \
    --allow-unauthenticated \
    --quiet

echo "================================================================="
echo "Service deployment completed successfully from source!"
echo "Cloud Run Sandboxes enabled for $SERVICE_NAME."
echo "================================================================="
