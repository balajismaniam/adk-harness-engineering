#!/usr/bin/env bash
# deploy_job.sh
# Automates the creation and deployment of the ADK Analysis runner to Google Cloud Run Jobs.

set -eo pipefail

echo "================================================================="
echo "Starting Google Cloud Run Job deployment pipeline..."
echo "================================================================="

# 1. Load and validate environment variables
if [ ! -f .env ]; then
    echo "  [ERROR] .env file not found. Please create one by copying .env.example."
    exit 1
fi

source .env

REQUIRED_VARS=(GOOGLE_CLOUD_PROJECT SA_NAME CLOUD_RUN_REGION GOOGLE_CLOUD_LOCATION GCS_BUCKET_NAME)
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "  [ERROR] Environment variable $var is empty. Please set it in your .env file."
        exit 1
    fi
done

echo "  [INFO] Environment variables validated:"
echo "         Project ID:       $GOOGLE_CLOUD_PROJECT"
echo "         Service Account:  $SA_NAME"
echo "         Region:           $CLOUD_RUN_REGION"
echo "         AI Location:      $GOOGLE_CLOUD_LOCATION"
echo "         GCS Bucket:       $GCS_BUCKET_NAME"

# 1.5 Enable required Google Cloud Service APIs
echo "  [INFO] Enabling required Google Cloud APIs..."
SERVICES=(
    "run.googleapis.com"
    "artifactregistry.googleapis.com"
    "cloudbuild.googleapis.com"
    "aiplatform.googleapis.com"
    "iam.googleapis.com"
)
for service in "${SERVICES[@]}"; do
    echo "         Enabling $service..."
    gcloud services enable "$service" --project="$GOOGLE_CLOUD_PROJECT"
done

echo "  [INFO] Verifying APIs are active and propagated..."
for service in "${SERVICES[@]}"; do
    attempts=0
    max_attempts=15
    until gcloud services list --enabled --project="$GOOGLE_CLOUD_PROJECT" --filter="config.name:$service" --format="value(config.name)" | grep -q "$service"; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge "$max_attempts" ]; then
            echo "  [ERROR] Timeout waiting for $service to propagate."
            exit 1
        fi
        echo "         Waiting for $service propagation ($attempts/$max_attempts)..."
        sleep 2
    done
done
echo "         All APIs verified active."

# 2. Setup IAM Service Account
echo "  [INFO] Setting up Service Account..."
SA_EMAIL="$SA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$SA_EMAIL" --project="$GOOGLE_CLOUD_PROJECT" &>/dev/null; then
    echo "         Service account $SA_EMAIL already exists. Skipping creation."
else
    gcloud iam service-accounts create "$SA_NAME" \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --description="ADK Runner Service Account" \
        --display-name="ADK Runner Service Account"
    echo "         Created service account $SA_EMAIL."
fi

echo "  [INFO] Granting Vertex AI User role to the service account..."
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/aiplatform.user" \
    --quiet &>/dev/null

echo "  [INFO] Granting Storage Admin role to the service account..."
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.admin" \
    --quiet &>/dev/null

echo "  [INFO] Granting Logging Log Writer role to the service account..."
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter" \
    --quiet &>/dev/null

echo "  [INFO] Granting Artifact Registry Writer role to the service account..."
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/artifactregistry.writer" \
    --quiet &>/dev/null

# 2.5 Setup Cloud Storage Bucket
echo "  [INFO] Setting up Google Cloud Storage Bucket..."
if gcloud storage buckets describe "gs://$GCS_BUCKET_NAME" --project="$GOOGLE_CLOUD_PROJECT" &>/dev/null; then
    echo "         GCS bucket gs://$GCS_BUCKET_NAME already exists. Skipping creation."
else
    gcloud storage buckets create "gs://$GCS_BUCKET_NAME" \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --location="$CLOUD_RUN_REGION"
    echo "         Created GCS bucket gs://$GCS_BUCKET_NAME."
fi

# 3. Create Artifact Registry Repository
echo "  [INFO] Setting up Artifact Registry..."
if gcloud artifacts repositories describe adk-repo --project="$GOOGLE_CLOUD_PROJECT" --location="$CLOUD_RUN_REGION" &>/dev/null; then
    echo "         Repository 'adk-repo' already exists. Skipping creation."
else
    gcloud artifacts repositories create adk-repo \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --repository-format=docker \
        --location="$CLOUD_RUN_REGION" \
        --description="Repository for ADK analysis images"
    echo "         Created repository 'adk-repo'."
fi

# 4. Build and Containerize using Cloud Build
IMAGE_TAG="$CLOUD_RUN_REGION-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/adk-repo/adk-analysis:latest"
echo "  [INFO] Submitting docker build to Cloud Build: $IMAGE_TAG..."
gcloud builds submit \
    --project="$GOOGLE_CLOUD_PROJECT" \
    --tag "$IMAGE_TAG" \
    --service-account="projects/$GOOGLE_CLOUD_PROJECT/serviceAccounts/$SA_EMAIL" \
    --gcs-log-dir="gs://$GCS_BUCKET_NAME/build_logs" \
    .

# 5. Create or Update Cloud Run Job
echo "  [INFO] Registering Cloud Run Job..."
if gcloud run jobs describe adk-analysis-job --project="$GOOGLE_CLOUD_PROJECT" --region="$CLOUD_RUN_REGION" &>/dev/null; then
    echo "         Job 'adk-analysis-job' already exists. Updating job configuration..."
    gcloud run jobs update adk-analysis-job \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --image "$IMAGE_TAG" \
        --service-account "$SA_EMAIL" \
        --region "$CLOUD_RUN_REGION" \
        --add-volume="name=adk-storage,type=cloud-storage,bucket=$GCS_BUCKET_NAME" \
        --add-volume-mount="volume=adk-storage,mount-path=/mnt/storage" \
        --set-env-vars GOOGLE_GENAI_USE_VERTEXAI="true",GOOGLE_CLOUD_LOCATION="$GOOGLE_CLOUD_LOCATION",GOOGLE_CLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT",STORAGE_MOUNT_PATH="/mnt/storage" \
        --task-timeout="30m" \
        --quiet
else
    gcloud run jobs create adk-analysis-job \
        --project="$GOOGLE_CLOUD_PROJECT" \
        --image "$IMAGE_TAG" \
        --service-account "$SA_EMAIL" \
        --region "$CLOUD_RUN_REGION" \
        --add-volume="name=adk-storage,type=cloud-storage,bucket=$GCS_BUCKET_NAME" \
        --add-volume-mount="volume=adk-storage,mount-path=/mnt/storage" \
        --set-env-vars GOOGLE_GENAI_USE_VERTEXAI="true",GOOGLE_CLOUD_LOCATION="$GOOGLE_CLOUD_LOCATION",GOOGLE_CLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT",STORAGE_MOUNT_PATH="/mnt/storage" \
        --task-timeout="30m" \
        --quiet
    echo "         Created Cloud Run Job 'adk-analysis-job'."
fi

echo "================================================================="
echo "Deployment completed successfully!"
echo "To execute all experiments, run:"
echo "  gcloud run jobs execute adk-analysis-job --project=$GOOGLE_CLOUD_PROJECT --region=$CLOUD_RUN_REGION"
echo "To run a specific Case Study (e.g. Case Study 4), run:"
echo "  gcloud run jobs execute adk-analysis-job --project=$GOOGLE_CLOUD_PROJECT --region=$CLOUD_RUN_REGION --args=\"--case-study=4\""
echo "================================================================="
