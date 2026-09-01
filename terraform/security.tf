# The security-group module takes cidr_ipv4 only — it has no source-security-group
# parameter — so intra-VPC access is expressed as the VPC CIDR rather than as an
# SG reference. Acceptable inside a single-tenant sandbox VPC.

module "jenkins_sg" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/security-group?ref=main"

  name        = "${var.project}-jenkins-sg"
  description = "Jenkins controller: SSH for Ansible, 8080 for the web UI"
  vpc_id      = module.vpc.vpc_id

  ingress_rules = [
    {
      description = "SSH for Ansible and manual access"
      from_port   = 22
      to_port     = 22
      ip_protocol = "tcp"
      cidr_ipv4   = var.admin_cidr
    },
    {
      description = "Jenkins web UI"
      from_port   = 8080
      to_port     = 8080
      ip_protocol = "tcp"
      cidr_ipv4   = var.admin_cidr
    },
    # --- observability: scraped by the monitoring server ---
    {
      description = "node_exporter, scraped by Prometheus"
      from_port   = 9100
      to_port     = 9100
      ip_protocol = "tcp"
      cidr_ipv4   = var.vpc_cidr
    },
    {
      description = "Jenkins /prometheus endpoint, scraped by Prometheus"
      from_port   = 8080
      to_port     = 8080
      ip_protocol = "tcp"
      cidr_ipv4   = var.vpc_cidr
    }
  ]
}

module "app_sg" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/security-group?ref=main"

  name        = "${var.project}-app-sg"
  description = "Deployment target: SSH from inside the VPC, HTTP from the internet"
  vpc_id      = module.vpc.vpc_id

  ingress_rules = [
    {
      description = "SSH from the Jenkins controller (same VPC)"
      from_port   = 22
      to_port     = 22
      ip_protocol = "tcp"
      cidr_ipv4   = var.vpc_cidr
    },
    {
      description = "SSH from the operator, for Ansible and debugging"
      from_port   = 22
      to_port     = 22
      ip_protocol = "tcp"
      cidr_ipv4   = var.admin_cidr
    },
    {
      description = "Application HTTP"
      from_port   = var.app_port
      to_port     = var.app_port
      ip_protocol = "tcp"
      cidr_ipv4   = "0.0.0.0/0"
    },
    {
      description = "node_exporter, scraped by Prometheus"
      from_port   = 9100
      to_port     = 9100
      ip_protocol = "tcp"
      cidr_ipv4   = var.vpc_cidr
    }
  ]
}