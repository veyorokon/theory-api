# terraform/backend.hcl  (example — don't commit real values)
bucket         = "your-tfstate-bucket"
key            = "theory/infra/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "terraform-locks"
