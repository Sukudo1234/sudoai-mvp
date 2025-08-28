# Terraform Backend Configuration
# This will be configured during initial setup

terraform {
  backend "s3" {
    # These values will be provided via backend-config during terraform init
    # bucket = "your-terraform-state-bucket"
    # key    = "sudoai-mvp/terraform.tfstate"  
    # region = "ap-south-1"
    
    # Enable state locking and consistency checking
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}