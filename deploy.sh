#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${PROJECT:?Set PROJECT in .env or in the shell}"
: "${OPENROUTER_MODEL:?Set OPENROUTER_MODEL to an available OpenRouter model ID}"
REGION="${REGION:-europe-west1}"
DB="${FIRESTORE_DATABASE:-customer-support}"
SETTINGS_SECRET="${SETTINGS_SECRET:-support-app-settings}"
SERVICE="customer-support-chatbot"
BUCKET="$PROJECT-support-chatbot"
SA="$SERVICE@$PROJECT.iam.gserviceaccount.com"
G=(gcloud --project "$PROJECT" --quiet)

# Check the settings secret by metadata before provisioning resources.
state=$("${G[@]}" secrets versions describe latest --secret "$SETTINGS_SECRET" --format='value(state)')
if [[ "$state" != ENABLED ]]; then
  printf 'Secret %s needs an enabled latest version.\n' "$SETTINGS_SECRET" >&2
  exit 1
fi

"${G[@]}" services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com iam.googleapis.com
"${G[@]}" firestore databases describe --database "$DB" >/dev/null 2>&1 ||
  "${G[@]}" firestore databases create --database "$DB" --location "$REGION" --edition standard --type firestore-native
"${G[@]}" storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
  "${G[@]}" storage buckets create "gs://$BUCKET" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention
"${G[@]}" iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  "${G[@]}" iam service-accounts create "$SERVICE" --display-name "Customer support chatbot"

for attempt in 1 2 3 4 5 6; do
  if "${G[@]}" storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member "serviceAccount:$SA" --role roles/storage.objectUser >/dev/null; then
    break
  fi
  [[ "$attempt" != 6 ]] || exit 1
  sleep 5
done

"${G[@]}" projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/datastore.user \
  --condition "expression=resource.name==\"projects/$PROJECT/databases/$DB\",title=support-firestore-database" >/dev/null
"${G[@]}" secrets add-iam-policy-binding "$SETTINGS_SECRET" --member "serviceAccount:$SA" \
  --role roles/secretmanager.secretAccessor >/dev/null

"${G[@]}" auth print-access-token | python3 seed_orders.py "$PROJECT" "$DB"
"${G[@]}" run deploy "$SERVICE" --source . --region "$REGION" --service-account "$SA" \
  --set-env-vars "PROJECT=$PROJECT,FIRESTORE_DATABASE=$DB,BUCKET_NAME=$BUCKET,OPENROUTER_MODEL=$OPENROUTER_MODEL" \
  --set-secrets "APP_SETTINGS=$SETTINGS_SECRET:latest" \
  --allow-unauthenticated --min-instances 0 --max-instances 2 --memory 512Mi
"${G[@]}" run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
