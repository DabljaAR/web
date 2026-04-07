# Remote state configuration (optional but recommended)
# Uncomment and configure to use GCS backend for state management
#
terraform {
  backend "gcs" {
    bucket = "dabljaar-terraform-state"
    prefix = "dabljaar/state"
  }
}
#
# Before using remote state, create the bucket:
# gsutil mb -l <REGION> gs://your-terraform-state-bucket
# gsutil versioning set on gs://your-terraform-state-bucket
