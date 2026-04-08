# DabljaAR Terraform Infrastructure

Terraform in this directory provisions infrastructure only.

## Scope

Included:
- VPC network and subnet
- Firewall rules (public, admin, internal, IAP SSH)
- Compute VM (with optional GPU)
- Persistent data disk
- GCS bucket provisioning
- Static external IP

Excluded:
- Application deployment and runtime orchestration
- Docker Compose startup or service bootstrap
- Repository cloning or app environment generation
- Application secret payload management

Optional host baseline bootstrap is supported via VM startup script variables
(`startup_script_enabled`, `deployment_user`) to install host dependencies such
as Docker and system packages. This does not run application containers.

## Deployment Bootstrap (Exact Manual Steps)

This section is the minimal setup to make first deploy succeed on a private repo.

### 1) Define the minimal required artifacts

Required:
- VM access key used by GitHub Actions (`GCP_VM_SSH_KEY`) for CI -> VM SSH.
- GitHub deploy key (read-only) used by VM for VM -> GitHub clone/pull.
- `.env.production` content in Secret Manager (`vm_env_secret_name`).
- VM startup bootstrap enabled (`startup_script_enabled = true`).
- VM service account enabled with Secret Manager access (`enable_vm_service_account = true`).

Not required for deployment correctness:
- Generating SSH keys on the VM at runtime.
- Using both deploy key and HTTPS token for the same clone path.
- Host hardening features (ufw/autoupdates) as a deployment blocker.

### 2) Create a GitHub deploy key pair locally

```bash
ssh-keygen -t ed25519 -C "dabljaar-vm-deploy" -f ./github_deploy_key -N ""
```

Add `./github_deploy_key.pub` in GitHub repo settings as a read-only Deploy Key.

### 3) Create/update required secrets in GCP Secret Manager

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud secrets describe env-production >/dev/null 2>&1 || \
    gcloud secrets create env-production --replication-policy=automatic
gcloud secrets versions add env-production --data-file=.env.production

gcloud secrets describe github-deploy-key >/dev/null 2>&1 || \
    gcloud secrets create github-deploy-key --replication-policy=automatic
gcloud secrets versions add github-deploy-key --data-file=./github_deploy_key
```

### 4) Set Terraform variables

In `terraform.tfvars`:

```hcl
startup_script_enabled = true
enable_vm_service_account = true
vm_env_secret_name = "env-production"
vm_git_deploy_key_secret_name = "github-deploy-key"
```

### 5) Apply Terraform and run bootstrap

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

For existing VMs, force startup script execution:

```bash
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo google_metadata_script_runner startup"
```

Fallback:

```bash
gcloud compute instances reset INSTANCE_NAME --zone=ZONE --project=PROJECT_ID
```

### 6) Verify bootstrap success

```bash
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo tail -n 200 /var/log/vm-bootstrap.log"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo test -f /var/lib/vm-bootstrap.done && echo bootstrap_ok || echo bootstrap_failed"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "docker --version && docker compose version"
gcloud compute ssh INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --command "sudo -u DEPLOYMENT_USER ssh -T git@github.com || true"
```

If bootstrap marker exists and Docker is present, GitHub Actions deploy should pass the preflight checks.

## Quick Start

1. Authenticate:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

2. Configure:

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars
```

3. Deploy:

```bash
terraform init
terraform plan
terraform apply
```

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

## Security Notes

- Public exposure should typically be limited to ports 80 and 443.
- Admin ports are restricted via `admin_cidr_blocks`.
- SSH access is intended through IAP.

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
