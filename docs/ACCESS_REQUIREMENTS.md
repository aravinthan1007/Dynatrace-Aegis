# Access requirements

This project can be changed locally without cloud credentials. GitHub and Google
Cloud access are only needed when you want to push changes, run CI, deploy, or
execute live onboarding.

## GitHub

Minimum access:

- Write access to the target GitHub repository.
- Permission to push a branch or open a pull request.
- Permission to read and update GitHub Actions if CI must run.

Useful local setup:

```bash
gh auth login
gh repo set-default <owner>/<repo>
git remote -v
```

For automation, use a GitHub token with only the scopes needed for the workflow:

- `contents:write` for pushing branches.
- `pull-requests:write` for opening PRs.
- `actions:read` or `actions:write` only if the workflow needs it.

## Google Cloud for Cloud Run onboarding

Needed project state:

- A target GCP project id.
- Billing enabled.
- `gcloud` installed and authenticated locally or in CI.
- Permission to enable project APIs.

Recommended IAM roles for the operator account:

- `roles/serviceusage.serviceUsageAdmin`
- `roles/run.admin`
- `roles/cloudbuild.builds.editor`
- `roles/artifactregistry.admin`
- `roles/iam.serviceAccountUser`
- `roles/secretmanager.admin`
- `roles/monitoring.viewer`

The runtime service account for the Cloud Run app needs:

- `roles/secretmanager.secretAccessor` on the Dynatrace token secret.

## Google Cloud for GKE Autopilot onboarding

The GKE path creates or configures GCP services, Pub/Sub, log sinks, IAM, and a
GKE Autopilot cluster. It needs broader access than the Cloud Run path.

Recommended IAM roles for the operator account:

- `roles/serviceusage.serviceUsageAdmin`
- `roles/container.admin`
- `roles/pubsub.admin`
- `roles/logging.configWriter`
- `roles/secretmanager.admin`
- `roles/iam.roleAdmin`
- `roles/resourcemanager.projectIamAdmin`
- `roles/monitoring.viewer`

If your organization blocks broad project IAM changes, create and approve the
custom Dynatrace deployment role separately, then grant only that custom role to
the onboarding operator.

## Dynatrace

For Cloud Run OTLP onboarding:

- Dynatrace environment URL.
- OTLP ingest token.
- OAuth client id and secret for DQL verification, if you want live grounding
  checks to run immediately.

For GKE/GCP metric and log onboarding:

- Dynatrace SaaS URL.
- Dynatrace access key with the required GCP services monitoring permissions.
- OAuth/DQL credentials if post-onboarding validation should query Grail.

## What I can do without more access

- Edit the repo locally.
- Add tests and run local unit tests.
- Generate post-onboarding DQL checks.
- Prepare commit messages, PR descriptions, and deployment commands.

## What needs your approval or credentials

- Push to GitHub.
- Run GitHub Actions.
- Deploy to Cloud Run.
- Execute live GCP onboarding.
- Create or modify IAM bindings, GKE clusters, Pub/Sub topics, log sinks, or
  Secret Manager secrets.
