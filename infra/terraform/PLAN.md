# Terraform scope

Terraform provisions **infrastructure and host bootstrap** only:

- VPC, firewall, GCS bucket, static IP, VM, data disk
- Optional Cloudflare DNS A records
- Optional Secret Manager bootstrap secrets + VM service account IAM
- VM startup script: Docker, data disk mount, `.env.production` + GitHub deploy key from Secret Manager

**Application deploy** (git pull, compose, migrations) stays in [`.github/workflows/deploy-gcp.yml`](../../.github/workflows/deploy-gcp.yml).

## Validation

```bash
terraform fmt -recursive
terraform init -backend=false
terraform validate
```
