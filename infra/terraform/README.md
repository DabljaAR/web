# DabljaAR Terraform Infrastructure

Terraform provisions GCP infrastructure, optional Cloudflare DNS, bootstrap secrets, and prepares a single VM for Docker Compose deployment via GitHub Actions.

Follow the steps **in order**. Skipping or reordering steps (especially DNS before apply, or secrets before bootstrap) causes failed applies or broken deploys.

---

## What Terraform creates

| Resource | Purpose |
|----------|---------|
| VPC, firewall, Cloud NAT | Network isolation and egress |
| Static external IP | Stable target for DNS A records |
| VM + data disk | Docker Compose host |
| GCS bucket | Model/media object storage |
| Secret Manager (optional) | `env-production`, `github-deploy-key` |
| Cloudflare A records (optional) | `app.yourbrand.tech`, `rabbitmq.app.yourbrand.tech`, `grafana.app.yourbrand.tech` |

**Not included:** app container deploy, Terraform CI, image registry, backups.

**Observability:** self-hosted on the VM via Docker Compose overlay ([`docs/observability.md`](../../docs/observability.md)) — not GCP Cloud Monitoring. The VM service account has `roles/logging.logWriter` and `roles/monitoring.metricWriter` for optional future GCP agent use, but the default stack is Loki + Grafana + VictoriaMetrics + Tempo.

---

## Prerequisites

1. GCP project with billing enabled.
2. `gcloud` and Terraform `>= 1.5` installed locally.
3. A **.tech** domain registered at [get.tech](https://get.tech/) (managed at [controlpanel.tech](https://controlpanel.tech/customer)).
4. A **free Cloudflare** account ([dash.cloudflare.com](https://dash.cloudflare.com)).
5. GitHub repo admin access (Deploy Keys + Actions secrets).
6. GCS bucket for Terraform state (one-time, step 1 below).

Authenticate to GCP:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

---

## Setup checklist (in order)

### Step 1 — Terraform remote state bucket (one-time)

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=us-central1

gsutil mb -l "$REGION" "gs://${PROJECT_ID}-terraform-state" 2>/dev/null || true
gsutil versioning set on "gs://${PROJECT_ID}-terraform-state"
```

Edit [`backend.tf`](backend.tf) if your bucket name differs:

```hcl
terraform {
  backend "gcs" {
    bucket = "YOUR_PROJECT_ID-terraform-state"
    prefix = "dabljaar/state"
  }
}
```

---

### Step 2 — SSH keys (two different keypairs)

You need **two** keys. Do not mix them up.

#### 2a — GitHub Actions → VM (deploy SSH)

Used by `.github/workflows/deploy-gcp.yml` to SSH into the VM.

```bash
ssh-keygen -t ed25519 -C "gha-vm-deploy" -f ./gha_vm_deploy_key -N ""
```

- **Private key** `gha_vm_deploy_key` → GitHub secret `GCP_VM_SSH_KEY` (step 9).
- **Public key** → Terraform variable `vm_ssh_public_key` (step 6).

Format for Terraform (one line; `USER` must match `deployment_user` in tfvars):

```text
ubuntu:ssh-ed25519 AAAA...comment gha-vm-deploy
```

#### 2b — VM → GitHub (read-only deploy key)

Used by the VM to `git clone` / `git pull` your private repo.

```bash
ssh-keygen -t ed25519 -C "vm-github-deploy" -f ./github_deploy_key -N ""
```

1. Open GitHub → **Settings → Deploy keys → Add deploy key**
2. Title: `gcp-vm-deploy`
3. Key: contents of `github_deploy_key.pub`
4. **Allow read access** only (do not enable write)

The **private** key `github_deploy_key` is read from `GP/keys/github_deploy_key` by Terraform automatically (step 5).

---

### Step 3 — Cloudflare zone + get.tech nameservers (one-time)

This enables **free** DNS automation for your `.tech` domain.

#### 3a — Add zone on Cloudflare

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → **Add a site**
2. Enter your apex zone, e.g. `yourbrand.tech`
3. Select **Free** plan
4. Cloudflare shows two nameservers, e.g. `ada.ns.cloudflare.com` and `bob.ns.cloudflare.com`

#### 3b — Point get.tech to Cloudflare

1. Log in at [controlpanel.tech](https://controlpanel.tech/customer)
2. Search your domain → **Order Information**
3. **Name Servers** → replace existing NS with Cloudflare's two nameservers → **Update**
4. Wait until Cloudflare shows the zone as **Active** (often 15–60 minutes; up to 24h)

Verify (optional):

```bash
dig +short NS yourbrand.tech
```

#### 3c — Cloudflare API token

1. Cloudflare → **My Profile → API Tokens → Create Token**
2. Use template **Edit zone DNS** or custom token with **Zone → DNS → Edit** on `yourbrand.tech`
3. Copy the token and export it in the **same shell** where you run Terraform:

```bash
export CLOUDFLARE_API_TOKEN=your_token_here
```

Use an **API Token** (from API Tokens), not the Global API Key. The token should contain only letters, numbers, hyphens, and underscores — no quotes, spaces, or `Bearer` prefix. Verify:

```bash
echo "$CLOUDFLARE_API_TOKEN" | wc -c   # should be > 1
```

---

### Step 4 — Production environment file content

Use [`.env.production.example`](../../.env.production.example) as a template.

**Subdomain setup (recommended):**

```bash
DOMAIN=app.yourbrand.tech
ACME_EMAIL=you@yourbrand.tech
```

Caddy also requests certificates for `rabbitmq.app.yourbrand.tech` and (when observability is enabled) `grafana.app.yourbrand.tech` (`Caddyfile.minimal` + `infra/observability/Caddyfile.grafana`).

When enabling observability, also set in `.env.production`:

```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=replace-with-strong-password
GRAFANA_BASIC_AUTH_USER=admin
GRAFANA_BASIC_AUTH_HASH=replace-with-bcrypt-hash   # caddy hash-password
```

Run `terraform apply` so `grafana.app.yourbrand.tech` resolves before the first observability deploy. Verify: `dig +short grafana.app.yourbrand.tech`.

You will paste the **full file contents** into the `env-production` secret in step 5.

---

### Step 5 — Secret source files

Terraform reads secret **contents from files in `.tf` code** (not from `file()` in `.tfvars` — that is not allowed).

Default paths (relative to `infra/terraform/`):

| Secret | Default file |
|--------|----------------|
| `env-production` | `../../.env.production` (repo root) |
| `github-deploy-key` | `../../../keys/github_deploy_key` |

Ensure both files exist before `terraform apply`.

Optional: copy `secrets.auto.tfvars.example` to `secrets.auto.tfvars` only if you need **custom paths**:

```hcl
env_production_file    = "/absolute/path/to/.env.production"
github_deploy_key_file = "/absolute/path/to/github_deploy_key"
```

**Alternative:** set `manage_secret_versions = false` in tfvars, apply, then:

```bash
gcloud secrets versions add env-production --data-file=../../.env.production
gcloud secrets versions add github-deploy-key --data-file=../../../keys/github_deploy_key
```

---

### Step 6 — Terraform variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`. Required changes:

| Variable | Example |
|----------|---------|
| `project_id` | your GCP project ID |
| `environment` | `prod` |
| `deployment_user` | `ubuntu` (must match SSH key user) |
| `dns_enabled` | `true` (only after Cloudflare zone is Active) |
| `dns_zone_name` | `yourbrand.tech` |
| `dns_app_subdomain` | `app` |
| `vm_ssh_public_key` | `ubuntu:ssh-ed25519 AAAA...` from step 2a |

Recommended:

```hcl
enable_spot            = false
enable_oslogin         = false
dns_proxied            = false
enable_deploy_ssh      = true   # required for GitHub Actions SSH deploy
deploy_ssh_cidr_blocks = ["0.0.0.0/0"]
admin_cidr_blocks      = ["YOUR_IP/32"]  # optional: direct Flower port access
```

---

### Step 6b — Pre-apply checks

Run these **before** `terraform apply`:

```bash
# Cloudflare zone must be Active (nameservers updated at get.tech)
dig +short NS yourbrand.tech

# No duplicate Secret Manager secrets (apply fails if they exist from manual gcloud)
gcloud secrets list --project=YOUR_PROJECT_ID | grep -E 'env-production|github-deploy-key'

# Secret source files exist
test -f ../../.env.production && test -f ../../../keys/github_deploy_key && echo ok

# Rotate weak credentials in .env.production before apply (POSTGRES_PASSWORD, FLOWER_BASIC_AUTH, etc.)
```

If `env-production` or `github-deploy-key` already exist, either `terraform import` them or delete and let Terraform recreate.

---

### Step 7 — Terraform init, plan, apply (first)

```bash
cd infra/terraform
export CLOUDFLARE_API_TOKEN="..."   # required when dns_enabled = true

terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Wait for VM bootstrap (~5–10 minutes). The plan creates **30 resources** including a new GCS models bucket and deploy SSH firewall rule.

---

### Step 8 — Sync models bucket + secret (required)

Terraform creates `dabljaar-prod-models-{suffix}`. Your app reads `S3_MODELS_BUCKET` from `.env.production` (uploaded to Secret Manager). **Update after first apply:**

```bash
cd infra/terraform
BUCKET="$(terraform output -raw storage_bucket_name)"
echo "New models bucket: $BUCKET"

# 1. Edit repo-root .env.production — set S3_MODELS_BUCKET to $BUCKET

# 2. Grant your HMAC key (S3_ACCESS_KEY_ID in .env) Storage Object Admin on the new bucket
#    GCP Console → Cloud Storage → bucket → Permissions → Grant access
#    Also ensure the HMAC key can access S3_MEDIA_BUCKET (separate media bucket)

# 3. Re-apply so env-production secret version updates
terraform apply -var-file=terraform.tfvars

# 4. If VM already bootstrapped, refresh env on host (or re-run startup script)
INSTANCE="$(terraform output -raw instance_name)"
ZONE="$(terraform output -raw instance_zone)"
gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command "sudo google_metadata_script_runner startup"
```

---

### Step 9 — Post-apply verification

```bash
terraform output external_ip
terraform output deploy_hostname
dig +short "$(terraform output -raw app_fqdn)"

INSTANCE="$(terraform output -raw instance_name)"
ZONE="$(terraform output -raw instance_zone)"
PROJECT="$(gcloud config get-value project)"

gcloud compute ssh "$INSTANCE" --zone="$ZONE" --project="$PROJECT" \
  --command "sudo test -f /var/lib/vm-bootstrap.done && docker compose version"
```

---

### Step 10 — GitHub Actions secrets

| Secret | Value |
|--------|-------|
| `GCP_VM_HOST` | `terraform output -raw deploy_hostname` |
| `GCP_VM_USER` | same as `deployment_user` |
| `GCP_VM_PORT` | `22` |
| `GCP_VM_SSH_KEY` | private key from step 2a |

```bash
gh secret set GCP_VM_HOST --body "$(terraform output -raw deploy_hostname)"
gh secret set GCP_VM_USER --body "ubuntu"
gh secret set GCP_VM_SSH_KEY < ./gha_vm_deploy_key
```

---

### Step 11 — Deploy application

Push to `main` or run the **Deploy to GCP VM** workflow. It checks `https://app.yourbrand.tech/api/health`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Cloudflare plan fails | `export CLOUDFLARE_API_TOKEN=...` in the same terminal; use API Token not Global API Key; zone must be Active |
| HTTPS / ACME fails | `dns_proxied = false`; DNS must point to VM IP |
| GHA SSH fails | `enable_deploy_ssh = true`; `enable_oslogin = false`; user matches `vm_ssh_public_key`; check `deploy_ssh` firewall rule exists |
| Models not loading from GCS | `S3_MODELS_BUCKET` must match `terraform output storage_bucket_name`; HMAC key needs bucket IAM |
| Git clone on VM fails | Deploy key on GitHub; `github-deploy-key` secret populated |
| Bootstrap incomplete | `sudo google_metadata_script_runner startup` on VM |
| Secret already exists | `gcloud secrets list`; import or delete before apply |

---

## Cleanup

```bash
terraform destroy -var-file=terraform.tfvars
```
