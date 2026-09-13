# Cloud Run Deployment Guide (SPEC-37)

Deploy the Travel Buddy backend to Google Cloud Run from reviewed main.
No secrets appear in this file or in the repository.

## Prerequisites

- Google Cloud SDK (`gcloud`) installed and authenticated
- An existing GCP project with billing enabled
- Cloud Run API enabled
- The rotated Google Maps API key with API restrictions only (not an
  Android application restriction, which is incompatible with server egress)

## 1. Enable APIs (one-time, PowerShell)

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

## 2. Choose a region

Pick a region close to the hosted Supabase database to reduce latency.
List available Cloud Run regions:

```powershell
gcloud run regions list
```

Set it for this session:

Owner decision 2026-09-07: Cloud Run region is `asia-south1` (Mumbai), matching
hosted Supabase. Do not deploy until PR #57 `android-compile` is green on a
commit that tracks `mobile/android/`.

```powershell
$REGION = "asia-south1"
```

## 3. Build and deploy from source

`gcloud run deploy --source .` builds the container image and deploys in one
step; no separate Artifact Registry repository is required.

From the repository root (reviewed main after SPEC-37 merge, or this draft
branch only if review explicitly allows a field-test deploy):

```powershell
$SERVICE = "travel-buddy"

gcloud run deploy $SERVICE `
  --source . `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --port 8080 `
  --memory 512Mi `
  --min-instances 0 `
  --max-instances 3 `
  --set-env-vars "TB_DEBUG=false,TB_ALLOW_ANONYMOUS=true"
```

## 4. Set secrets in the Cloud Run console

Navigate to Cloud Run > travel-buddy > Edit & Deploy New Revision > Variables
& Secrets.

Set these environment variables (values from your secrets, never in this repo):

| Variable | Description |
|---|---|
| `TB_SUPABASE_URL` | Hosted Supabase project URL |
| `TB_SUPABASE_KEY` | Service-role key (never in Flutter) |
| `TB_LITELLM_API_KEY` | LLM provider key |
| `TB_GOOGLE_MAPS_API_KEY` | Rotated Maps API key (API restrictions only) |
| `TB_OPENWEATHER_API_KEY` | OpenWeather API key |

Leave `TB_SUPABASE_JWT_SECRET` unset for anonymous field testing.

`TB_DEBUG` and `TB_ALLOW_ANONYMOUS` were set in the deploy command above.

## 5. Configure health check

In the Cloud Run console under Health checks:

- **Startup probe**: HTTP GET `/api/v1/health`, port 8080, initial delay 5s
- **Liveness probe**: HTTP GET `/api/v1/health`, port 8080, period 30s

## 6. Verify from a non-laptop network (PowerShell)

```powershell
$HOSTED = "https://<your-service>.run.app"

# Health (liveness only)
$h = Invoke-RestMethod "$HOSTED/api/v1/health"
if ($h.status -ne "healthy") { throw "Health check failed" }
Write-Host "Health: OK"

# Anonymous trip list (fixed canonical UUID-v4 for verification)
$headers = @{ "Authorization" = "Anonymous aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" }
$trips = Invoke-RestMethod "$HOSTED/api/v1/trips" -Headers $headers
if ($trips -eq $null) { throw "Trip list failed" }
Write-Host "Trip list: OK ($($trips.Count) trips)"

# Trip read (replace TRIP_ID after creating a corridor)
# $trip = Invoke-RestMethod "$HOSTED/api/v1/trip/TRIP_ID" -Headers $headers
```

Configuration booleans are in startup logs (Cloud Run > Logs) and the revision
environment panel, not in the public health response.

## Cloud Shell alternative

If running from Google Cloud Shell instead of the owner's laptop:

```bash
REGION="asia-south1"
SERVICE="travel-buddy"

gcloud run deploy $SERVICE \
  --source . \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "TB_DEBUG=false,TB_ALLOW_ANONYMOUS=true"
```

## Security reminders

- The Supabase service-role key must never appear in Flutter code, the repo,
  or chat. Set it only in the Cloud Run console.
- `TB_DEBUG=false` prevents impersonation headers.
- The Google Maps key must be the rotated replacement, not the leaked one.
- The Maps key must have API restrictions (not Android application
  restrictions) since Cloud Run makes server-side requests.
- Verify provider connectivity from the hosted service using Cloud Run logs
  after the first trip creation.
