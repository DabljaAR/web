# DabljaAR Terraform Infrastructure

Terraform in this directory provisions the GCP infrastructure and can fully
bootstrap a VM host for Docker Compose deployment.

## Scope

Included:
- VPC network and subnet
- Firewall rules (public, admin, internal, IAP SSH)
- Compute VM (CPU or optional GPU)
- Persistent data disk
- GCS bucket provisioning
- Static external IP
- Optional startup bootstrap for host preparation

Excluded:
- Running app containers as part of `terraform apply`
- GitHub Actions secret creation in your GitHub repository
- GitHub Actions deployment workflow in your GitHub repository

## Assumptions

Before running Terraform, ensure:

1. A GCP project exists and billing is enabled.
2. Required APIs are enabled (at minimum Compute Engine and Secret Manager).
3. You are authenticated locally:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

4. If you need GPU workers, quota is available in your selected zone.
5. Your deployment user (`deployment_user`) already exists on the VM image.
6. You have a production env file (`.env.production`) ready.
7. You can create GitHub Deploy Keys for your repository.
8. You have created a GCP bucket for terraform state.
```bash
gsutil mb -l us-central1 gs://dabljaar-terraform-state
gsutil versioning set on gs://dabljaar-terraform-state
```

## Full Automation Flow (Infra + VM Prepared for Deploy)

### 1) Create GitHub deploy key pair

```bash
ssh-keygen -t ed25519 -C "dabljaar-vm-deploy" -f ./github_deploy_key -N ""
```

Add `./github_deploy_key.pub` to the GitHub repository as a read-only Deploy Key.

### 2) Create Secret Manager secrets

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud secrets describe env-production >/dev/null 2>&1 || \
  gcloud secrets create env-production --replication-policy=automatic
gcloud secrets versions add env-production --data-file=.env.production

gcloud secrets describe github-deploy-key >/dev/null 2>&1 || \
  gcloud secrets create github-deploy-key --replication-policy=automatic
gcloud secrets versions add github-deploy-key --data-file=./github_deploy_key
```

### 3) Configure Terraform variables

Copy and edit `terraform.tfvars`:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Required host-bootstrap fields:

```hcl
startup_script_enabled = true
enable_vm_service_account = true
deployment_user = "ubuntu"
vm_env_secret_name = "env-production"
vm_git_deploy_key_secret_name = "github-deploy-key"
```

Recommended production settings:

```hcl
enable_spot = false
public_ports = [80, 443]
admin_ports = [22, 5555, 9001]
admin_cidr_blocks = ["YOUR_IP/32"]
```

### 4) Apply Terraform

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

### 5) Validate bootstrap completed

```bash
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo tail -n 200 /var/log/vm-bootstrap.log"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo test -f /var/lib/vm-bootstrap.done && echo bootstrap_ok || echo bootstrap_failed"
```

### 6) Validate host readiness for deployment

```bash
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "docker --version && docker compose version"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "nvidia-smi || true"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo -u DEPLOYMENT_USER ssh -T git@github.com || true"
```

If all checks pass, GitHub Actions deployment (`.github/workflows/deploy-gcp.yml`) can clone/pull and run Docker Compose without manual VM setup.

## What Bootstrap Does

When `startup_script_enabled = true`, the VM startup script:

1. Installs baseline packages (`curl`, `git`, `jq`, `rsync`, etc.).
2. Detects, formats (first run), and mounts the persistent disk at `/mnt/data`.
3. Installs Docker Engine + Compose plugin.
4. Installs NVIDIA Container Toolkit when NVIDIA drivers are present.
5. Moves Docker and containerd storage to `/mnt/data`.
6. Configures Docker daemon logging and `data-root`.
7. Adds `deployment_user` to the `docker` group.
8. Creates app/runtime directories with ownership and permissions.
9. Pulls `.env.production` from Secret Manager (optional).
10. Installs GitHub SSH deploy key from Secret Manager (optional).
11. Writes bootstrap marker file at `/var/lib/vm-bootstrap.done`.

## Data Disk Layout

The bootstrap configures disk usage to reduce boot disk pressure:

- `/mnt/data/docker`: Docker image/layer/volume runtime storage
- `/mnt/data/containerd`: containerd state storage
- `/mnt/data/volumes`: host-managed bind-volume space for app usage

This keeps large Docker artifacts off the boot disk.

## GitHub Actions Deployment

The GitHub Actions deployment workflow is defined in `.github/workflows/deploy-gcp.yml`.

It is triggered by pushing to the `main` branch.

Make sure to add the following secrets to the GitHub repository:
- `GCP_VM_HOST`: The public IP of the GCP VM.
- `GCP_VM_USER`: The username to use to SSH into the GCP VM.
- `GCP_VM_PORT`: The port to use to SSH into the GCP VM. (22)
- `GCP_VM_SSH_KEY`: The SSH key to use to SSH into the GCP VM. (The private key of the SSH key pair you created in step 1)

## GPU Runtime Notes

For GPU-enabled deployments:

1. Use a GPU-compatible VM/image in Terraform.
2. Confirm `nvidia-smi` works on the VM.
3. Deploy with GPU compose overlay in app repo:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yaml \
  -f docker-compose.prod.yml \
  -f docker-compose.gpu.yml up -d --build
```

If `nvidia-smi` fails, the NVIDIA driver/image is not ready; fix that first.

## Troubleshooting

### Bootstrap did not run

- Check script logs: `/var/log/vm-bootstrap.log`
- Check marker: `/var/lib/vm-bootstrap.done`
- Re-run startup script manually:

```bash
sudo google_metadata_script_runner startup
```

### Docker still using boot disk

```bash
docker info | grep -i "Docker Root Dir"
```

Expected value: `/mnt/data/docker`

### GitHub clone/pull fails on VM

- Verify deploy key secret exists and contains the private key.
- Verify VM service account has `roles/secretmanager.secretAccessor`.
- Validate SSH from deployment user:

```bash
sudo -u DEPLOYMENT_USER ssh -T git@github.com
```

### GPU containers fail to start

- Verify toolkit:

```bash
nvidia-ctk --version
docker info | grep -i runtime
```

- Ensure `docker-compose.gpu.yml` is included during deploy.

## Module Structure

```text
terraform/
├── main.tf                    # root module wiring
├── variables.tf               # root inputs
├── outputs.tf                 # infra outputs
├── locals.tf                  # naming and labels
├── versions.tf                # terraform/provider constraints
├── backend.tf                 # remote state backend config
├── terraform.tfvars.example   # sample values
│
└── modules/
    ├── network/               # VPC/subnet/router/NAT
    ├── firewall/              # firewall rules
    ├── storage/               # GCS bucket
    ├── iam/                   # optional service account and IAM bindings
    └── compute/               # VM, disk, external IP
```

## Key Inputs

- `project_id`
- `project_name`
- `environment`
- `region`
- `zone`
- `subnet_cidr`
- `public_ports`
- `admin_cidr_blocks`
- `admin_ports`
- `machine_type`
- `gpu_type`
- `gpu_count`
- `enable_spot`
- `startup_script_enabled`
- `deployment_user`
- `enable_vm_service_account`
- `vm_env_secret_name`
- `vm_git_deploy_key_secret_name`
- `boot_disk_image`
- `boot_disk_size`
- `data_disk_size`

## Key Outputs

- `instance_name`
- `external_ip`
- `network_id`
- `subnet_id`
- `storage_bucket_name`
- `firewall_rule_ids`
- `ssh_command`

## Validation

```bash
terraform fmt -recursive
terraform init -backend=false
terraform validate
terraform plan -var-file=terraform.tfvars
```

## Cleanup

```bash
terraform destroy
```
