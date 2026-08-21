# Terraform

Provisions bare infrastructure and stops there. No `user_data` — package
installation is Ansible's job.

```
providers.tf   aws + tls + local, pinned to the sandbox-user profile
variables.tf   every knob, with defaults that work unedited
network.tf     vpc → igw → public subnet → route table
security.tf    jenkins_sg (22, 8080) and app_sg (22 from VPC, 80 public)
compute.tf     key pair + two instances, tagged Role=jenkins / Role=app
outputs.tf     IPs, DNS names, ready-to-paste SSH commands
```

All resources come from
[terraform-aws-modules](https://github.com/Smiley2507/terraform-aws-modules),
used unmodified and pinned to `?ref=main`.

## Usage

```bash
terraform init && terraform validate && terraform apply
terraform output -raw app_private_ip   # → the APP_HOST pipeline parameter
```

## Notes

**Security group scoping.** The module accepts `cidr_ipv4` only — no
source-security-group parameter — so "SSH from the Jenkins server" is expressed
as the VPC CIDR. Fine in a single-tenant sandbox; in a shared VPC you would
extend the module.

**The private key.** `apply` writes `cicd-key.pem` at mode 0400; Ansible reads
it from there and it becomes the `ec2_ssh` Jenkins credential. It is also in
the state file in plaintext — `.gitignore` excludes both.
