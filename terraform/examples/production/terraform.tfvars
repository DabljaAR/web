project_id   = "your-production-project"
region       = "us-central1"
zone         = "us-central1-a"
app_repo_url = "https://github.com/your-org/dabljaar.git"

# Restrict admin access to specific IPs
admin_cidr_blocks = [
  # "YOUR_OFFICE_IP/32",
  # "YOUR_VPN_IP/32",
]

# Set secrets via environment variables:
# export TF_VAR_db_password="$(openssl rand -base64 32)"
# export TF_VAR_secret_key="$(openssl rand -base64 64)"
# export TF_VAR_minio_access_key="$(openssl rand -base64 16)"
# export TF_VAR_minio_secret_key="$(openssl rand -base64 32)"
