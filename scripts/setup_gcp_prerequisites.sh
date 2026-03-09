#!/bin/bash
# ============================================================================
# GCP Prerequisites Setup for Gemini Agent Engine
# ============================================================================
set -e

PROJECT_ID="${PROJECT_ID:-[your-project-id]}"
REGION="${REGION:-us-central1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Step 0: Set Project
echo ""
echo "============================================================================"
echo "Step 0: Setting up GCP project"
echo "============================================================================"
gcloud config set project $PROJECT_ID
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
log_success "Project Number: $PROJECT_NUMBER"

# Step 1: Enable APIs
echo ""
echo "============================================================================"
echo "Step 1: Enabling required APIs"
echo "============================================================================"
APIS=(
    "aiplatform.googleapis.com"
    "secretmanager.googleapis.com"
    "cloudbuild.googleapis.com"
    "storage.googleapis.com"
    "iam.googleapis.com"
    "iamcredentials.googleapis.com"
    "drive.googleapis.com"
    "docs.googleapis.com"
    "slides.googleapis.com"
    "sheets.googleapis.com"
    "run.googleapis.com"
)
for api in "${APIS[@]}"; do
    log_info "Enabling $api..."
    gcloud services enable $api --quiet
done
log_success "All required APIs enabled."

# Step 2: Create Service Account
echo ""
echo "============================================================================"
echo "Step 2: Creating Service Account"
echo "============================================================================"
SA_NAME="agent-engine-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Service account $SA_NAME already exists."
else
    log_info "Creating service account $SA_NAME..."
    gcloud iam service-accounts create $SA_NAME \
        --project=$PROJECT_ID \
        --display-name="Gemini Agent Engine Service Account"
    log_success "Service account created: $SA_EMAIL"
fi

# Step 3: Assign IAM Roles
echo ""
echo "============================================================================"
echo "Step 3: Assigning IAM roles"
echo "============================================================================"
SA_ROLES=(
    "roles/aiplatform.user"
    "roles/secretmanager.secretAccessor"
    "roles/storage.objectViewer"
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
    "roles/serviceusage.serviceUsageConsumer"
)
for role in "${SA_ROLES[@]}"; do
    log_info "Granting $role to $SA_NAME..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --condition=None \
        --quiet
done
log_success "All roles assigned."

# Step 4: Configure Service Agents
echo ""
echo "============================================================================"
echo "Step 4: Configuring GCP-managed Service Agents"
echo "============================================================================"
SERVICE_AGENTS=(
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-cc.iam.gserviceaccount.com"
)
for sa in "${SERVICE_AGENTS[@]}"; do
    log_info "Granting serviceUsageConsumer to $sa..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$sa" \
        --role="roles/serviceusage.serviceUsageConsumer" \
        --condition=None \
        --quiet 2>/dev/null || log_warning "Could not grant role to $sa (may not exist yet)"
done
log_success "Service agents configured."

# Step 5: Create Staging Bucket
echo ""
echo "============================================================================"
echo "Step 5: Setting up Staging Bucket"
echo "============================================================================"
STAGING_BUCKET="${PROJECT_ID}_cloudbuild"
if gsutil ls -b gs://$STAGING_BUCKET > /dev/null 2>&1; then
    log_warning "Staging bucket gs://$STAGING_BUCKET already exists."
else
    log_info "Creating staging bucket gs://$STAGING_BUCKET..."
    gsutil mb -l $REGION gs://$STAGING_BUCKET
    log_success "Staging bucket created."
fi

# Step 6: Create Secret for API Key
echo ""
echo "============================================================================"
echo "Step 6: Setting up Secret Manager for API Key"
echo "============================================================================"
SECRET_NAME="gemini-api-key"
if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Secret $SECRET_NAME already exists."
else
    log_info "Creating secret $SECRET_NAME..."
    gcloud secrets create $SECRET_NAME \
        --project=$PROJECT_ID \
        --replication-policy="automatic"
    log_success "Secret created."
fi

log_info "Add your Gemini API key:"
echo ""
echo "  echo 'YOUR_GEMINI_API_KEY' | gcloud secrets versions add $SECRET_NAME --data-file=-"
echo ""

# Step 7: Create Secret for OAuth Client Config
echo ""
echo "============================================================================"
echo "Step 7: Setting up OAuth Client Config Secret"
echo "============================================================================"
OAUTH_SECRET_NAME="oauth-client-config"
if gcloud secrets describe $OAUTH_SECRET_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Secret $OAUTH_SECRET_NAME already exists."
else
    log_info "Creating secret $OAUTH_SECRET_NAME..."
    gcloud secrets create $OAUTH_SECRET_NAME \
        --project=$PROJECT_ID \
        --replication-policy="automatic"
    log_success "Secret created."
fi

log_info "Add your OAuth client config:"
echo ""
echo "  echo '{\"client_id\": \"YOUR_CLIENT_ID\", \"client_secret\": \"YOUR_CLIENT_SECRET\"}' | \\"
echo "    gcloud secrets versions add $OAUTH_SECRET_NAME --data-file=-"
echo ""

# Summary
echo ""
echo "============================================================================"
echo "Setup Complete!"
echo "============================================================================"
echo ""
log_success "Project: $PROJECT_ID"
log_success "Region: $REGION"
log_success "Service Account: $SA_EMAIL"
log_success "Staging Bucket: gs://$STAGING_BUCKET"
log_success "Secret Name: $SECRET_NAME"
echo ""
echo "Next Steps:"
echo "  1. Add Gemini API key to Secret Manager"
echo "  2. Create OAuth Client ID in Cloud Console (APIs & Credentials > Web application)"
echo "  3. Add OAuth client config to Secret Manager (see above)"
echo "  4. Deploy OAuth callback: cd cloud-run-oauth-callback && bash deploy.sh"
echo "  5. Add callback URL as redirect URI in OAuth Client ID settings"
echo "  6. Deploy Agent Engine: python scripts/deploy_agent_engine.py --project $PROJECT_ID"
echo ""
