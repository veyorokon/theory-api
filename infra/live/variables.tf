variable "project" { type = string }
variable "env"     { type = string } # dev|staging|prod
variable "region"  { type = string; default = "us-east-1" }

# App image (push your Django image to ECR or any registry)
variable "web_image" {
  description = "Container image for Django ASGI (daphne/uvicorn) e.g., <acct>.dkr.ecr...:tag"
  type        = string
}

# Sizing
variable "web_desired_count" { type = number; default = 2 }
variable "web_cpu"           { type = number; default = 512 }   # 0.5 vCPU
variable "web_memory"        { type = number; default = 1024 }  # 1 GB

# DB settings
variable "db_name"           { type = string; default = "appdb" }
variable "db_username"       { type = string; default = "appuser" }

# Networking CIDRs
variable "vpc_cidr"          { type = string; default = "10.20.0.0/16" }
variable "public_subnets"    { type = list(string); default = ["10.20.0.0/24","10.20.1.0/24"] }
variable "private_subnets"   { type = list(string); default = ["10.20.10.0/24","10.20.11.0/24"] }