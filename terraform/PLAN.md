# Terraform Infrastructure Plan

## Scope

Terraform provisions infrastructure primitives only:
- VPC network and subnet
- Firewall rules
- VM instance (optional GPU)
- Persistent data disk
- GCS storage bucket
- Static external IP

Terraform does not manage application lifecycle tasks such as:
- cloning repositories
- generating app runtime environment files
- starting or managing Docker Compose services
- app-level secret population

## Implementation Notes

1. Keep root modules limited to network, firewall, storage, and compute.
2. Keep storage provisioning as infrastructure concern.
3. Remove app-runtime startup scripts from compute metadata.
4. Keep outputs infrastructure-centric.
5. Keep example configs free of app/runtime variables.

## Validation

```bash
terraform fmt -recursive
terraform init -backend=false
terraform validate
terraform plan -var-file=terraform.tfvars
```
