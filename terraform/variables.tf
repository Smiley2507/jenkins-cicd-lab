variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1"
}

variable "aws_profile" {
  description = "Named profile in ~/.aws/credentials used for this deployment"
  type        = string
  default     = "sandbox-user"
}

variable "project" {
  description = "Prefix used for resource names"
  type        = string
  default     = "cicd"
}

# --- network ---------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.20.1.0/24"
}

variable "availability_zone" {
  description = "AZ for the public subnet"
  type        = string
  default     = "eu-west-1a"
}

# --- compute ---------------------------------------------------------------

variable "jenkins_instance_type" {
  default = "t3.small"
}

variable "app_instance_type" {
  default = "t3.micro"
}

variable "jenkins_root_volume_size" {
  default = 20
}

variable "app_root_volume_size" {
  default = 10
}

variable "ami_name_filter" {
  description = "AMI name pattern. Standard Amazon Linux 2023 — the 2023.* prefix with an explicit kernel excludes the ecs / minimal / neuron variants, which carry larger snapshots and software we don't want."
  type        = string
  default     = "al2023-ami-2023.*-kernel-6.1-x86_64"
}

variable "ami_id" {
  description = "Pinned AMI. Resolving the latest AL2023 at plan time makes every plan want to replace the instances whenever AWS publishes a new image."
  type        = string
  default     = "ami-0b9b7988c01535dd6"
}
# --- access ----------------------------------------------------------------

variable "admin_cidr" {
  description = "CIDR allowed to reach SSH and the Jenkins UI from outside the VPC"
  type        = string
  default     = "0.0.0.0/0"
}

variable "app_port" {
  description = "Host port the application is published on"
  type        = number
  default     = 80
}

variable "private_key_path" {
  description = "Local path where the generated private key is written. Consumed by Ansible and by the Jenkins ec2_ssh credential."
  type        = string
  default     = "./cicd-key.pem"
}

variable "tags" {
  description = "Default tags applied to every resource"
  type        = map(string)
  default = {
    Project     = "jenkins-cicd-lab"
    Environment = "sandbox"
    ManagedBy   = "terraform"
  }
}
