terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.56" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  backend "s3" {
    bucket         = "visureel-tf-state"   # <--- set to bootstrap output
    key            = "dev/app.tfstate"     # use workspaces or per-env keys
    region         = "us-east-1"
    dynamodb_table = "visureel-tf-lock"    # <--- set to bootstrap output
    encrypt        = true
  }
}