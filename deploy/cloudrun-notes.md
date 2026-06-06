# Cloud Run Notes

## Recommended deployment shape

Use two Cloud Run services:

1. `aegis-demo-app`
   Runs `demo_app.main:app` and receives live traffic from load generation.
2. `aegis-dashboard`
   Runs `dashboard.server:app`, serves the hero UI, and orchestrates the Aegis workflow.

This split is simpler than forcing both FastAPI apps into one container. It also mirrors the local Docker Compose setup and makes `AEGIS_DEMO_APP_URL` explicit.

## Images

- Dashboard image: `deploy/Dockerfile.agent`
- Demo app image: same base image pattern, but run `uvicorn demo_app.main:app --host 0.0.0.0 --port 8080`

## Environment variables

### `aegis-demo-app`

- `STORE_BASE_LATENCY_MS`
- `DT_OTLP_ENDPOINT`
- `DT_OTLP_TOKEN`

### `aegis-dashboard`

- `GOOGLE_API_KEY`
- `GEMINI_MODEL`
- `DT_ENVIRONMENT`
- `DT_PLATFORM_TOKEN`
- `DT_API_TOKEN`
- `DT_MCP_SERVER_VERSION`
- `DT_MCP_DISABLE_TELEMETRY`
- `AEGIS_DEMO_APP_URL=https://aegis-demo-app-<hash>-uc.a.run.app`
- `BURN_ABORT`
- `SLO_TARGET`
- `BURN_WINDOW_SECONDS`
- `LATENCY_THRESHOLD_MS`
- Optional: `GITHUB_TOKEN`, `GITHUB_REPO`, `SLACK_WEBHOOK`

## Deployment order

1. Deploy `aegis-demo-app`.
2. Capture its public URL.
3. Deploy `aegis-dashboard` with `AEGIS_DEMO_APP_URL` pointing at the demo app URL.
4. Run a smoke test from the dashboard UI.

## Suggested commands

### Build and push demo app image

```bash
docker build -f deploy/Dockerfile.demo_app -t us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-demo-app:latest .
docker push us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-demo-app:latest
```

### Deploy demo app

```bash
gcloud run deploy aegis-demo-app \
  --image us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-demo-app:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars STORE_BASE_LATENCY_MS=40 \
  --port 8080
```

### Build and push dashboard image

```bash
docker build -f deploy/Dockerfile.agent -t us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-dashboard:latest .
docker push us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-dashboard:latest
```

### Deploy dashboard

```bash
gcloud run deploy aegis-dashboard \
  --image us-central1-docker.pkg.dev/PROJECT_ID/aegis/aegis-dashboard:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars AEGIS_DEMO_APP_URL=https://aegis-demo-app-<hash>-uc.a.run.app \
  --port 8080
```

## Local-to-cloud checklist

1. Local Docker Compose run works end to end.
2. `/metrics/recent` reacts within seconds during chaos.
3. Dashboard shows approval, burn line, and abort banner.
4. Dynatrace `verify_dql` succeeds against the live tenant.
5. Real GitHub PR flow is tested before recording the final demo.
