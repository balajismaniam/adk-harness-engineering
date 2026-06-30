#!/usr/bin/env bash
# cleanup_resources.sh
# Safely and interactively tears down the deployed ADK Analysis Google Cloud Run Job and resources.

set -eo pipefail

# 1. Load and validate environment variables
if [ ! -f .env ]; then
    echo "  [ERROR] .env file not found. Cannot proceed with resource mapping."
    exit 1
fi

source .env

REQUIRED_VARS=(GOOGLE_CLOUD_PROJECT SA_NAME CLOUD_RUN_REGION GCS_BUCKET_NAME)
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "  [ERROR] Environment variable $var is empty. Cannot determine cleanup targets."
        exit 1
    fi
done

SA_EMAIL="$SA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"

echo "================================================================="
echo "WARNING: YOU ARE ABOUT TO PERMANENTLY DELETE THE FOLLOWING GCP RESOURCES:"
echo "================================================================="
echo "  1. Cloud Run Job:      adk-analysis-job"
echo "  2. Artifact Registry:  adk-repo (All container images will be lost)"
echo "  3. Service Account:    $SA_EMAIL (Permissions will be revoked)"
echo "  4. GCS Bucket:         gs://$GCS_BUCKET_NAME (All persisted results will be lost)"
echo "================================================================="
echo "Project ID: $GOOGLE_CLOUD_PROJECT"
echo "Region:     $CLOUD_RUN_REGION"
echo "================================================================="
echo ""

# Explicitly prompt the user to confirm deletion
read -p "Are you sure you want to permanently delete all these resources? (yes/no): " confirmation

if [ "$confirmation" != "yes" ]; then
    echo "Cleanup cancelled. No resources were deleted."
    exit 0
fi

echo ""
echo "Starting cleanup process..."
echo "-----------------------------------------------------------------"

# Delete Cloud Run Job (without --quiet, let gcloud prompt)
echo "  [INFO] Deleting Cloud Run Job: adk-analysis-job..."
if gcloud run jobs describe adk-analysis-job --project="$GOOGLE_CLOUD_PROJECT" --region="$CLOUD_RUN_REGION" &>/dev/null; then
    gcloud run jobs delete adk-analysis-job --project="$GOOGLE_CLOUD_PROJECT" --region="$CLOUD_RUN_REGION"
else
    echo "         Job 'adk-analysis-job' not found. Skipping."
fi

# Delete Artifact Registry Repository (without --quiet)
echo "  [INFO] Deleting Artifact Registry Repository: adk-repo..."
if gcloud artifacts repositories describe adk-repo --project="$GOOGLE_CLOUD_PROJECT" --location="$CLOUD_RUN_REGION" &>/dev/null; then
    gcloud artifacts repositories delete adk-repo --project="$GOOGLE_CLOUD_PROJECT" --location="$CLOUD_RUN_REGION"
else
    echo "         Repository 'adk-repo' not found. Skipping."
fi

# Delete IAM Service Account (without --quiet)
echo "  [INFO] Deleting Service Account: $SA_EMAIL..."
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$GOOGLE_CLOUD_PROJECT" &>/dev/null; then
    gcloud iam service-accounts delete "$SA_EMAIL" --project="$GOOGLE_CLOUD_PROJECT"
else
    echo "         Service Account '$SA_EMAIL' not found. Skipping."
fi

# Delete GCS Bucket (without --quiet)
echo "  [INFO] Deleting GCS Bucket: gs://$GCS_BUCKET_NAME..."
if gcloud storage buckets describe "gs://$GCS_BUCKET_NAME" --project="$GOOGLE_CLOUD_PROJECT" &>/dev/null; then
    gcloud storage buckets delete "gs://$GCS_BUCKET_NAME" --project="$GOOGLE_CLOUD_PROJECT"
else
    echo "         GCS bucket gs://$GCS_BUCKET_NAME not found. Skipping."
fi

echo "-----------------------------------------------------------------"
echo "Cleanup complete!"
echo "================================================================="
