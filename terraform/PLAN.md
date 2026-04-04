# Terraform GCP Infrastructure Plan for DabljaAR

## Problem Statement

Deploy the DabljaAR video dubbing platform (FastAPI + React + Celery + AI models) on GCP using Terraform. The app requires:
- **GPU compute** for AI workloads (Whisper STT, NLLB NMT, MMS TTS)
- **Docker Compose** orchestration for services
- Custom NMT models stored in **Cloud Storage**
- Proper networking with firewall rules
- **Lowest cost possible** using Spot VMs

## Proposed Approach

Deploy a **Spot GPU VM** (n1-standard-4 + T4) running Docker Compose. Use modular Terraform with best practices for maintainability and reusability.

---

## Architecture Overview

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
│  │  │   │  ~$85/mo (70% discount)                                │  │  │ │
│  │  │   │                                                        │  │  │ │
│  │  │   │  Docker Compose Stack:                                 │  │  │ │
│  │  │   │  ├─ PostgreSQL 16    ├─ FastAPI Backend               │  │  │ │
│  │  │   │  ├─ Redis 7          ├─ React Frontend                │  │  │ │
│  │  │   │  ├─ MinIO            ├─ Celery Workers (AI)           │  │  │ │
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

---

## Terraform Best Practices Applied

### 1. Module Structure
- **Single responsibility**: Each module handles one concern
- **Loose coupling**: Modules communicate via outputs/inputs only
- **Reusability**: Modules can be used in other projects

### 2. Code Organization
- **Consistent naming**: `{project}-{env}-{resource}` pattern
- **Locals for computed values**: Reduce repetition, centralize logic
- **Variable validation**: Catch errors early with constraints
- **Sensitive variables**: Mark secrets as `sensitive = true`

### 3. State Management
- **Remote backend**: GCS bucket for state (optional but recommended)
- **State locking**: Prevent concurrent modifications

### 4. Resource Management
- **Lifecycle rules**: `prevent_destroy` for critical resources
- **Depends_on**: Explicit dependencies where needed
- **Labels/Tags**: Consistent labeling for cost tracking

---

## Implementation Todos

### Phase 1: Root Module Setup
- **tf-root-structure**: Create root module with main.tf, variables.tf, outputs.tf, versions.tf, locals.tf, backend.tf
- **tf-provider-config**: Configure google/google-beta providers, enable required APIs

### Phase 2: Networking Module
- **tf-network-module**: Create modules/network/ with VPC, subnet, router, NAT
- **tf-firewall-module**: Create modules/firewall/ with configurable rules (public vs admin ports)

### Phase 3: IAM Module
- **tf-iam-module**: Create modules/iam/ with service account, role bindings, workload identity

### Phase 4: Storage Module
- **tf-storage-module**: Create modules/storage/ with GCS bucket, lifecycle rules, IAM bindings

### Phase 5: Secrets Module
- **tf-secrets-module**: Create modules/secrets/ with Secret Manager secrets for credentials

### Phase 6: Compute Module
- **tf-compute-module**: Create modules/compute/ with Spot VM, GPU, instance template
- **tf-startup-script**: Create startup.sh.tpl with auto-recovery, model sync, docker-compose

### Phase 7: Root Integration
- **tf-root-main**: Wire all modules together in root main.tf
- **tf-outputs**: Define comprehensive outputs (URLs, SSH, troubleshooting)

### Phase 8: Documentation
- **tf-readme**: Comprehensive README with usage, cost breakdown, troubleshooting
- **tf-examples**: Create examples/ directory with different configurations
- **tf-tfvars**: Create terraform.tfvars.example with documentation

---

## Key Technical Decisions

### 1. Machine Type: Spot VM (Lowest Cost)

| Config | vCPUs | RAM | GPU | On-Demand | **Spot Price** |
|--------|-------|-----|-----|-----------|----------------|
| n1-standard-4 + T4 | 4 | 15GB | T4 (16GB) | ~$280/mo | **~$85/mo** |

**Spot VM Considerations:**
- ⚠️ Can be preempted with 30s notice
- ✅ Auto-restart on preemption (via instance template)
- ✅ Persistent disk survives preemption (data safe)
- ✅ Startup script re-syncs models and restarts services

### 2. Spot VM Recovery Strategy
```
Preemption → VM terminated → Auto-restart (same zone or fallback)
                                    ↓
                            Startup script runs:
                            1. Mount persistent disk
                            2. Sync models from GCS (incremental)
                            3. docker-compose up -d
                            4. Health check → ready (~2-3 min)
```

### 3. Disk Configuration
| Disk | Size | Type | Purpose |
|------|------|------|---------|
| Boot | 50GB | pd-balanced | OS + Docker images |
| Data | 100GB | pd-balanced | PostgreSQL, Redis, MinIO, models |

*Data disk persists across preemptions* — no data loss.

### 4. Firewall Rules (Modular)
```hcl
# Public access (anyone)
public_ports = [80, 443, 5173, 8000]

# Admin access (restricted IPs)
admin_ports  = [22, 5555, 9000, 9001]
admin_cidrs  = ["YOUR_IP/32"]
```

### 5. Secrets Management
Using **Secret Manager** (not env vars in Terraform state):
- `db-password`
- `secret-key`
- `minio-access-key`
- `minio-secret-key`

Startup script fetches secrets via:
```bash
gcloud secrets versions access latest --secret="db-password"
```

---

## File Structure (Highly Modular)

```
terraform/
├── main.tf                    # Root: module calls only
├── variables.tf               # Root: input variables with validation
├── outputs.tf                 # Root: user-facing outputs
├── locals.tf                  # Root: computed values, naming conventions
├── versions.tf                # Provider version constraints
├── backend.tf                 # Remote state configuration (GCS)
├── terraform.tfvars.example   # Example configuration
├── README.md                  # Usage documentation
│
├── modules/
│   ├── network/
│   │   ├── main.tf            # VPC, subnet, router, Cloud NAT
│   │   ├── variables.tf       # network_name, subnet_cidr, region
│   │   └── outputs.tf         # network_id, subnet_id, subnet_self_link
│   │
│   ├── firewall/
│   │   ├── main.tf            # Firewall rules (public + admin)
│   │   ├── variables.tf       # public_ports, admin_ports, admin_cidrs
│   │   └── outputs.tf         # firewall_rule_ids
│   │
│   ├── iam/
│   │   ├── main.tf            # Service account, IAM bindings
│   │   ├── variables.tf       # account_id, roles, project_id
│   │   └── outputs.tf         # service_account_email, sa_key (if needed)
│   │
│   ├── storage/
│   │   ├── main.tf            # GCS bucket, lifecycle, IAM
│   │   ├── variables.tf       # bucket_name, location, retention_days
│   │   └── outputs.tf         # bucket_name, bucket_url
│   │
│   ├── secrets/
│   │   ├── main.tf            # Secret Manager secrets
│   │   ├── variables.tf       # secret_ids, secret_values (sensitive)
│   │   └── outputs.tf         # secret_ids (for IAM binding)
│   │
│   └── compute/
│       ├── main.tf            # Spot VM, instance template, GPU
│       ├── variables.tf       # machine_type, gpu_type, zone, disk_sizes
│       ├── outputs.tf         # instance_ip, instance_name, ssh_command
│       └── templates/
│           └── startup.sh.tpl # Startup script template
│
└── examples/
    ├── minimal/               # Bare minimum deployment
    │   ├── main.tf
    │   └── terraform.tfvars
    └── production/            # Full setup with monitoring
        ├── main.tf
        └── terraform.tfvars
```

---

## Module Interface Design

### Root main.tf (Example)
```hcl
locals {
  project     = var.project_id
  environment = var.environment
  name_prefix = "${var.project_name}-${var.environment}"
  
  common_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

module "network" {
  source       = "./modules/network"
  name_prefix  = local.name_prefix
  region       = var.region
  subnet_cidr  = var.subnet_cidr
  labels       = local.common_labels
}

module "firewall" {
  source        = "./modules/firewall"
  name_prefix   = local.name_prefix
  network_id    = module.network.network_id
  public_ports  = [80, 443, 5173, 8000]
  admin_ports   = [22, 5555, 9000, 9001]
  admin_cidrs   = var.admin_cidr_blocks
}

module "iam" {
  source       = "./modules/iam"
  name_prefix  = local.name_prefix
  project_id   = var.project_id
  gcs_bucket   = module.storage.bucket_name
  secret_ids   = module.secrets.secret_ids
}

module "storage" {
  source        = "./modules/storage"
  name_prefix   = local.name_prefix
  location      = var.region
  labels        = local.common_labels
}

module "secrets" {
  source = "./modules/secrets"
  
  secrets = {
    "db-password"      = var.db_password
    "secret-key"       = var.secret_key
    "minio-access-key" = var.minio_access_key
    "minio-secret-key" = var.minio_secret_key
  }
  
  name_prefix = local.name_prefix
  project_id  = var.project_id
}

module "compute" {
  source = "./modules/compute"
  
  name_prefix          = local.name_prefix
  zone                 = var.zone
  machine_type         = var.machine_type
  gpu_type             = var.gpu_type
  spot                 = true  # Enable Spot VM
  
  network_self_link    = module.network.network_self_link
  subnet_self_link     = module.network.subnet_self_link
  service_account_email = module.iam.service_account_email
  
  boot_disk_size       = 50
  data_disk_size       = 100
  
  gcs_model_bucket     = module.storage.bucket_name
  app_repo_url         = var.app_repo_url
  
  labels               = local.common_labels
}
```

---

## Startup Script Features (startup.sh.tpl)

```bash
#!/bin/bash
set -euo pipefail

# 1. Logging
exec > >(tee /var/log/startup.log) 2>&1
echo "=== Startup script started at $(date) ==="

# 2. Wait for GPU driver
until nvidia-smi; do sleep 5; done

# 3. Mount data disk (persistent across preemptions)
DISK_DEV="/dev/disk/by-id/google-${data_disk_name}"
MOUNT_POINT="/mnt/data"
if ! mountpoint -q $MOUNT_POINT; then
  mkdir -p $MOUNT_POINT
  mount -o discard,defaults $DISK_DEV $MOUNT_POINT || \
    (mkfs.ext4 -F $DISK_DEV && mount -o discard,defaults $DISK_DEV $MOUNT_POINT)
fi

# 4. Fetch secrets from Secret Manager
export DB_PASSWORD=$(gcloud secrets versions access latest --secret="${name_prefix}-db-password")
export SECRET_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-secret-key")
export MINIO_ACCESS_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-minio-access-key")
export MINIO_SECRET_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-minio-secret-key")

# 5. Sync models from GCS (incremental - fast on restart)
mkdir -p /opt/models
gsutil -m rsync -r gs://${model_bucket}/ /opt/models/

# 6. Clone/update app repo
APP_DIR="/opt/app"
if [ -d "$APP_DIR/.git" ]; then
  cd $APP_DIR && git pull
else
  git clone ${app_repo_url} $APP_DIR
fi

# 7. Create .env file
cat > $APP_DIR/.env <<EOF
DATABASE_URL=postgresql+asyncpg://postgres:$DB_PASSWORD@postgres:5432/dabljaar
SECRET_KEY=$SECRET_KEY
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=$MINIO_ACCESS_KEY
MINIO_SECRET_KEY=$MINIO_SECRET_KEY
MINIO_BUCKET_NAME=dablaja-videos
NMT_MODEL_URL=/opt/models/nmt-v4
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
EOF

# 8. Symlink persistent volumes
ln -sfn /mnt/data/postgres $APP_DIR/postgres_data
ln -sfn /mnt/data/redis $APP_DIR/redis_data
ln -sfn /mnt/data/minio $APP_DIR/minio_data

# 9. Start services
cd $APP_DIR
docker compose up -d

echo "=== Startup script completed at $(date) ==="
```

---

## Cost Summary

| Resource | Spot Price | Notes |
|----------|------------|-------|
| n1-standard-4 (Spot) | ~$30/mo | 4 vCPU, 15GB RAM |
| NVIDIA T4 (Spot) | ~$55/mo | 16GB VRAM |
| Boot disk (50GB) | ~$4/mo | pd-balanced |
| Data disk (100GB) | ~$8/mo | pd-balanced |
| GCS bucket | ~$2/mo | Model storage |
| External IP | ~$3/mo | Static IP |
| **Total** | **~$100/mo** | 70%+ savings vs on-demand |

---

## Spot VM Caveats & Mitigations

| Risk | Mitigation |
|------|------------|
| Preemption during job | Celery `acks_late=True` — unfinished tasks retry |
| Data loss | Persistent data disk survives preemption |
| Long startup time | Incremental model sync (gsutil rsync) |
| No availability | Set `automatic_restart = true` + zone fallback |

---

## Notes

- Spot VMs have **24-hour max lifetime** — will be preempted at least daily
- Consider **Committed Use Discounts** if running 24/7 long-term (cheaper than Spot)
- Add **Cloud Monitoring** alerts for preemption events
- For production, consider **Managed Instance Group** with auto-healing
