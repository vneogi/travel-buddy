# Cloud Run Deployment Guide (SPEC-37)

Deploy the Travel Buddy backend to Google Cloud Run from reviewed main.
No secrets appear in this file or in the repository.

## Prerequisites

- Google Cloud SDK (`gcloud`) installed and authenticated
- An existing GCP project with billing enabled
- Cloud Run API and Artifact Registry API enabled
- The rotated Google Maps API key (never the leaked one)

## 1. Enable APIs (one-time)

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

## 2. Build and push the container image

From the repository root (on reviewed main):

```bash
export GCP_PROJECT=$(gcloud config get-value project)
export REGION=us-central1
export SERVICE=travel-buddy

gcloud builds submit --tag ${REGION}-docker.pkg.dev/${GCP_PROJECT}/cloud-run-source-deploy/${SERVICE}
```

## 3. Deploy to Cloud Run

```bash
gcloud run deploy ${SERVICE} \
  --image ${REGION}-docker.pkg.dev/${GCP_PROJECT}/cloud-run-source-deploy/${SERVICE} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "TB_DEBUG=false,TB_ALLOW_ANONYMOUS=true"
```

## 4. Set secrets in the Cloud Run console

Navigate to Cloud Run > travel-buddy > Edit & Deploy New Revision > Variables & Secrets.

Set these environment variables (values from your secrets, never in this repo):

| Variable | Description |
|---|---|
| `TB_SUPABASE_URL` | Hosted Supabase project URL |
| `TB_SUPABASE_KEY` | Service-role key (never in Flutter) |
| `TB_LITELLM_API_KEY` | LLM provider key |
| `TB_GOOGLE_MAPS_API_KEY` | Rotated Maps API key |
| `TB_OPENWEATHER_API_KEY` | OpenWeather API key |

Leave `TB_SUPABASE_JWT_SECRET` unset for anonymous field testing.

`TB_DEBUG` and `TB_ALLOW_ANONYMOUS` were set in the deploy command above.

## 5. Configure health check

In the Cloud Run console under Health checks:

- **Startup probe**: HTTP GET `/api/v1/health`, port 8080, initial delay 5s
- **Liveness probe**: HTTP GET `/api/v1/health`, port 8080, period 30s

## 6. Verify from a non-laptop network

```bash
HOSTED_URL=https://<your-service>.run.app

# Health (booleans only, no secrets)
curl -s ${HOSTED_URL}/api/v1/health | python3 -m json.tool

# Expected: debug_mode=false, llm_key_present=true, supabase_configured=true

# Anonymous trip list
curl -s -H "X-Device-ID: field-test-device-1" ${HOSTED_URL}/api/v1/trips

# Trip read (replace TRIP_ID)
curl -s -H "X-Device-ID: field-test-device-1" ${HOSTED_URL}/api/v1/trip/TRIP_ID
```

## Security reminders

- The Supabase service-role key must never appear in Flutter code, the repo,
  or chat. Set it only in the Cloud Run console.
- `TB_DEBUG=false` prevents impersonation headers.
- The Google Maps key must be the rotated replacement, not the leaked one.
- Application and API restrictions should remain on the Maps key.
