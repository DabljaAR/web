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
