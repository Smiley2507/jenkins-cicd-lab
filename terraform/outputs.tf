output "jenkins_public_ip" {
  description = "Public IP of the Jenkins controller"
  value       = module.jenkins_server.public_ip
}

output "jenkins_public_dns" {
  description = "Public DNS of the Jenkins controller"
  value       = module.jenkins_server.public_dns
}

output "jenkins_url" {
  description = "Jenkins web UI"
  value       = "http://${module.jenkins_server.public_ip}:8080"
}

output "app_public_ip" {
  description = "Public IP of the deployment target"
  value       = module.app_server.public_ip
}

output "app_public_dns" {
  description = "Public DNS of the deployment target — use this for the accessibility screenshot"
  value       = module.app_server.public_dns
}

output "app_url" {
  description = "Deployed application URL"
  value       = "http://${module.app_server.public_dns}"
}

output "app_private_ip" {
  description = "Private IP of the app server. This is the APP_HOST the Jenkins deploy stage SSHes to."
  value       = module.app_server.private_ip
}

output "key_name" {
  description = "Name of the generated AWS key pair"
  value       = module.key_pair.key_name
}

output "private_key_path" {
  description = "Local path of the generated private key"
  value       = module.key_pair.private_key_path
}

output "ssh_jenkins" {
  description = "SSH command for the Jenkins controller"
  value       = "ssh -i ${var.private_key_path} ec2-user@${module.jenkins_server.public_ip}"
}

output "ssh_app" {
  description = "SSH command for the app server"
  value       = "ssh -i ${var.private_key_path} ec2-user@${module.app_server.public_ip}"
}

# Convenience block: everything you need to paste into Jenkins job config.
output "jenkins_job_env" {
  description = "Values to set as the APP_HOST/APP_URL environment in the pipeline"
  value = {
    APP_HOST = module.app_server.private_ip
    APP_URL  = "http://${module.app_server.public_dns}"
  }
}
