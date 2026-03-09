#!/bin/bash
set -e

PROJECT_ID="${PROJECT_ID:?PROJECT_ID must be set}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="workspace-oauth-callback"

echo "Building and deploying Cloud Run service: $SERVICE_NAME"

gcloud run deploy $SERVICE_NAME \
    --project=$PROJECT_ID \
    --region=$REGION \
    --source=. \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
    --allow-unauthenticated \
    --memory=256Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --quiet

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --project=$PROJECT_ID \
    --region=$REGION \
    --format='value(status.url)')

echo ""
echo "Deployed: $SERVICE_URL"
echo ""
echo "IMPORTANT: Add this redirect URI to your OAuth Client ID:"
echo "  ${SERVICE_URL}/callback"
echo ""
echo "Auth URL for users:"
echo "  ${SERVICE_URL}/auth/{user_id}"
echo ""
