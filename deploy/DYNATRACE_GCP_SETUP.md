# Dynatrace monitoring for Aegis on Google Cloud Run

This describes how to get Aegis's Cloud Run services monitored by Dynatrace. Every path
below is gated on **Dynatrace tokens with the correct scopes** — the current `dt0c01`
tokens return `401` because they lack ingest/installer scopes.

Tenant: `https://wkf10640.apps.dynatrace.com` · OTLP/API host: `https://wkf10640.live.dynatrace.com`

## Path A — App traces & metrics via OTLP (recommended, already wired)

The demo app already exports OTLP (`demo_app/otel_setup.py`). It only needs an ingest token.

1. Dynatrace → **Access Tokens** → create a token with scopes:
   `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest` (optional).
2. Set on the demo app and redeploy:
   ```bash
   gcloud run services update aegis-demo-app --region us-central1 \
     --update-env-vars DT_OTLP_ENDPOINT=https://wkf10640.live.dynatrace.com/api/v2/otlp,DT_OTLP_TOKEN=<ingest-token>
   ```
3. Verify: demo-app logs stop showing `Failed to export span batch 401`, and in Dynatrace
   `fetch spans | filter service.name == "aegis-demo-app" | summarize count()` returns > 0.

## Path B — Deep monitoring via OneAgent code injection

Heavier; gives full-stack app insights. Assets provided:
`deploy/Dockerfile.demo_app.oneagent` and `deploy/cloudbuild.oneagent.yaml`.

1. Create a token with the **InstallerDownload** (PaaS) scope.
2. Build (Cloud Build, so the PaaS token is a build arg):
   ```bash
   gcloud builds submit --config deploy/cloudbuild.oneagent.yaml \
     --substitutions _DT_API_URL=https://wkf10640.live.dynatrace.com/api,_DT_PAAS_TOKEN=<paas-token>,_TECH=all .
   ```
3. Deploy the built image with the runtime connection vars:
   ```bash
   gcloud run deploy aegis-demo-app \
     --image us-central1-docker.pkg.dev/<PROJECT_ID>/cloud-run-source-deploy/aegis-demo-app-oneagent:latest \
     --region us-central1 --allow-unauthenticated --port 8080 \
     --set-env-vars DT_TENANT=wkf10640,DT_CONNECTION_POINT=https://wkf10640.live.dynatrace.com:443
   ```

## Path C — Cloud Run infrastructure metrics (dynatrace-gcp-monitor)

Pulls platform metrics (request count, CPU, instances) from the GCP Operations API.

1. Token scopes: `metrics.ingest`, `entities.read`, `entities.write`, `extensions.read`,
   `extensions.write`, `extensionConfigurations.write`, `extensionEnvironment.write`.
2. GCP: enable `monitoring`, `cloudfunctions`/`run`, and grant the deploy service account
   `roles/monitoring.viewer`.
3. In Cloud Shell:
   ```bash
   wget -q "https://github.com/dynatrace-oss/dynatrace-gcp-monitor/releases/latest/download/helm-deployment-package.tar"
   tar -xvf helm-deployment-package.tar && chmod +x helm-deployment-package/deploy-helm.sh
   # edit helm-deployment-package/dynatrace-gcp-monitor/values.yaml: API token + URL; enable cloud_run_revision
   ./helm-deployment-package/deploy-helm.sh
   ```

## Dashboard + Notebook

The installed Dynatrace MCP (v0.13.0) exposes `execute_dql`/`list_problems` etc. but **no
create-dashboard/notebook tool**, so those are created via the Documents API with a platform
token scoped `document:documents:write` (and `storage:*:read` for the queries). Once OTLP data
is flowing, the dashboard/notebook are built from queries like:

```
timeseries avg(dt.service.request.response_time), by:{dt.entity.service}
fetch spans | filter service.name == "aegis-demo-app" | summarize requests = count(), by:{span.name}
```
