# DabljaAR Terraform Infrastructure

Modular Terraform configuration for deploying the DabljaAR video dubbing platform on GCP with GPU support.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              GCP Project                                  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                         VPC Network                                  │ │
│  │  ┌───────────────────────────────────────────────────────────────┐  │ │
│  │  │                      Public Subnet                             │  │ │
│  │  │                                                                │  │ │
│  │  │   ┌────────────────────────────────────────────────────────┐  │  │ │
│  │  │   │  SPOT VM (n1-standard-4 + NVIDIA T4)                   │  │  │ │
│  │  │   │                                                        │  │  │ │
│  │  │   │  Docker Compose Stack:                                 │  │  │ │
│  │  │   │  ├─ PostgreSQL 16    ├─ FastAPI Backend               │  │  │ │
│  │  │   │  ├─ Redis 7          ├─ React Frontend                │  │  │ │
│  │  │   │  ├─ MinIO            ├─ Celery Workers (AI/GPU)       │  │  │ │
│  │  │   │  └─ Flower           └─ /opt/models (from GCS)        │  │  │ │
│  │  │   └────────────────────────────────────────────────────────┘  │  │ │
│  │  └───────────────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │   GCS Bucket     │  │ Service Account  │  │   Secret Manager       │  │
│  │   (AI Models)    │  │ (minimal perms)  │  │   (credentials)        │  │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) >= 1.5.0
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- GCP project with billing enabled

### 2. Authenticate

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 3. Configure

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 4. Deploy

```bash
terraform init
terraform plan
terraform apply
```

### 5. Upload AI Models

```bash
# Get the bucket name from outputs
BUCKET=$(terraform output -raw model_bucket)

# Upload your models
gsutil -m cp -r /path/to/nmt-v4 gs://$BUCKET/
```

## Cost Estimate

| Resource | Spot Price | Notes |
|----------|------------|-------|
| n1-standard-4 (Spot) | ~$30/mo | 4 vCPU, 15GB RAM |
| NVIDIA T4 (Spot) | ~$55/mo | 16GB VRAM |
| Boot disk (50GB) | ~$4/mo | pd-balanced |
| Data disk (100GB) | ~$8/mo | pd-balanced |
| GCS bucket | ~$2/mo | Model storage |
| External IP | ~$3/mo | Static IP |
| **Total** | **~$100/mo** | 70%+ savings vs on-demand |

## Module Structure

```
terraform/
├── main.tf                    # Root: module calls
├── variables.tf               # Root: input variables
├── outputs.tf                 # Root: outputs
├── locals.tf                  # Root: computed values
├── versions.tf                # Provider versions
├── backend.tf                 # Remote state (optional)
├── terraform.tfvars.example   # Example configuration
│
└── modules/
    ├── network/               # VPC, subnet, NAT
    ├── firewall/              # Firewall rules
    ├── iam/                   # Service account
    ├── storage/               # GCS bucket
    ├── secrets/               # Secret Manager
    └── compute/               # Spot VM with GPU
```

## Inputs

| Name | Description | Default |
|------|-------------|---------|
| `project_id` | GCP project ID | (required) |
| `project_name` | Short name for resources | `dabljaar` |
| `environment` | dev/staging/prod | `dev` |
| `region` | GCP region | `us-central1` |
| `zone` | GCP zone | `us-central1-a` |
| `machine_type` | VM machine type | `n1-standard-4` |
| `gpu_type` | GPU type | `nvidia-tesla-t4` |
| `enable_spot` | Use Spot VM | `true` |
| `admin_cidr_blocks` | IPs for admin access | `[]` |

## Outputs

| Name | Description |
|------|-------------|
| `frontend_url` | Frontend application URL |
| `backend_url` | Backend API URL |
| `api_docs_url` | Swagger documentation |
| `ssh_command` | SSH access command |
| `model_bucket` | GCS bucket for models |

## Spot VM Recovery

Spot VMs can be preempted but auto-recover:

1. **Preemption** → VM terminates
2. **Auto-restart** → VM restarts (same zone)
3. **Startup script** runs:
   - Mount persistent data disk
   - Sync models from GCS (incremental)
   - Start Docker Compose
4. **Ready** → ~2-3 minutes

Data on the persistent disk survives preemption.

## Security

- Admin ports (SSH, Flower, MinIO) restricted to `admin_cidr_blocks`
- Secrets stored in Secret Manager (not Terraform state)
- Service account with minimal permissions
- IAP SSH access enabled for secure tunneling

### Secure Access via IAP Tunnel

```bash
# SSH via IAP (no public SSH exposure needed)
gcloud compute ssh INSTANCE_NAME --zone=ZONE --tunnel-through-iap

# Port forward admin services
gcloud compute ssh INSTANCE_NAME --zone=ZONE --tunnel-through-iap -- \
  -L 5555:localhost:5555 \
  -L 9001:localhost:9001
```

## Troubleshooting

### View startup logs
```bash
$(terraform output -raw view_startup_logs)
```

### Check GPU status
```bash
$(terraform output -raw check_gpu_status)
```

### View Docker logs
```bash
$(terraform output -raw view_docker_logs)
```

### SSH into instance
```bash
$(terraform output -raw ssh_command)
```

## Cleanup

```bash
terraform destroy
```

## License

MIT
