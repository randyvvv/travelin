#!/usr/bin/env bash
# Deploys Travelin: travelin-api and travelin-merchant to Cloud Run, and the PWA plus
# security rules to Firebase Hosting.
#
#   scripts/deploy.sh            # everything, in the right order
#   scripts/deploy.sh api        # one part: api | merchant | web
#
# Needs gcloud (logged in, project set), npm, and the secrets places-api-key,
# travelin-signing-key, and merchant-signing-key in Secret Manager. web/.env.local must
# hold the Firebase web config; VITE_API_URL is set here from the deployed API.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast2}"
BUCKET="${BUCKET:-$PROJECT.firebasestorage.app}"
FAST_MODEL="${FAST_MODEL:-gemini-3.8-flash}"
PLANNER_MODEL="${PLANNER_MODEL:-gemini-4-argon}"
WEB_ORIGINS="${WEB_ORIGINS:-https://$PROJECT.web.app,https://$PROJECT.firebaseapp.com}"

if [ -z "$PROJECT" ]; then
  echo "No project set. Run: gcloud config set project <project-id>" >&2
  exit 1
fi

url_of() {
  gcloud run services describe "$1" --region "$REGION" --project "$PROJECT" \
    --format='value(status.url)' 2>/dev/null || true
}

require_url() {
  local url
  url="$(url_of "$1")"
  if [ -z "$url" ]; then
    echo "$1 isn't deployed yet. Run: scripts/deploy.sh ${1#travelin-}" >&2
    exit 1
  fi
  echo "$url"
}

deploy_api() {
  local merchant_url env_file
  merchant_url="$(url_of travelin-merchant)"
  # ALLOWED_ORIGINS contains commas, which --set-env-vars would split on.
  env_file="$(mktemp)"
  cat > "$env_file" <<EOF
GOOGLE_CLOUD_PROJECT: "$PROJECT"
GOOGLE_CLOUD_LOCATION: "global"
STORAGE_BUCKET: "$BUCKET"
FAST_MODEL: "$FAST_MODEL"
PLANNER_MODEL: "$PLANNER_MODEL"
MERCHANT_URL: "${merchant_url:-https://merchant-not-deployed-yet.invalid}"
ALLOWED_ORIGINS: "$WEB_ORIGINS"
EOF
  gcloud run deploy travelin-api --source api --region "$REGION" --project "$PROJECT" \
    --service-account "travelin-api@$PROJECT.iam.gserviceaccount.com" \
    --allow-unauthenticated --min-instances 1 --no-cpu-throttling \
    --timeout 600 --memory 1Gi \
    --env-vars-file "$env_file" \
    --set-secrets "PLACES_API_KEY=places-api-key:latest,TRAVELIN_SIGNING_KEY=travelin-signing-key:latest"
  rm -f "$env_file"
}

deploy_merchant() {
  local api_url
  api_url="$(require_url travelin-api)"
  gcloud run deploy travelin-merchant --source merchant --region "$REGION" --project "$PROJECT" \
    --service-account "travelin-merchant@$PROJECT.iam.gserviceaccount.com" \
    --allow-unauthenticated --min-instances 1 --memory 512Mi \
    --set-env-vars "TRAVELIN_JWKS_URL=$api_url/.well-known/jwks.json" \
    --set-secrets "MERCHANT_SIGNING_KEY=merchant-signing-key:latest"
}

link_api_to_merchant() {
  local merchant_url
  merchant_url="$(require_url travelin-merchant)"
  gcloud run services update travelin-api --region "$REGION" --project "$PROJECT" \
    --update-env-vars "MERCHANT_URL=$merchant_url"
}

deploy_web() {
  local api_url
  api_url="$(require_url travelin-api)"
  if [ ! -f web/.env.local ]; then
    echo "web/.env.local is missing. Copy web/.env.example and fill in the Firebase config." >&2
    exit 1
  fi
  # Variables already in the environment override .env files in Vite.
  (cd web && npm ci && VITE_API_URL="$api_url" npm run build)
  npx --yes firebase-tools deploy --only hosting,firestore,storage --project "$PROJECT"
}

case "${1:-all}" in
  api) deploy_api ;;
  merchant) deploy_merchant ;;
  web) deploy_web ;;
  all)
    deploy_api
    deploy_merchant
    link_api_to_merchant
    deploy_web
    ;;
  *)
    echo "Usage: scripts/deploy.sh [api|merchant|web|all]" >&2
    exit 1
    ;;
esac

echo
echo "API:      $(url_of travelin-api)"
echo "Merchant: $(url_of travelin-merchant)"
echo "Web:      https://$PROJECT.web.app"
