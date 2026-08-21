# Ansible

Configures whatever Terraform provisioned. Discovery is dynamic — there is no
static inventory file to keep in sync.

```
ansible.cfg              points at the dynamic inventory and the TF-generated key
inventory.aws_ec2.yml    amazon.aws.aws_ec2, keyed_groups on the Role tag
group_vars/all.yml       pinned versions and shared paths
site.yml                 common everywhere, then per-role plays
roles/common/            dnf update, Docker engine, Compose v2 plugin
roles/jenkins/           Corretto 21, Jenkins LTS, jenkins→docker group
roles/appserver/         /opt/weather-app, compose file, nginx conf, prune cron
```

## The contract with Terraform

Terraform sets `Role = "jenkins"` / `Role = "app"` on the instances. The
inventory plugin turns those into the groups `role_jenkins` and `role_app`.
That tag string is the entire interface — change it in `terraform/compute.tf`
and you must change `keyed_groups` here to match.

Hosts are also filtered by `Project=jenkins-cicd-lab` (set via `default_tags`),
so Ansible can never wander onto an unrelated instance in the same account.

## Usage

```bash
ansible-galaxy collection install -r requirements.yml
ansible-inventory --graph
ansible-playbook site.yml
```

## Notes

**nginx config.** `nginx_conf_src` points at `../nginx/default.conf` — the repo
root copy is the single source of truth, shared with the local dev stack. The
appserver role copies it to the host and a handler reloads nginx in place.

**Compose v2.** Amazon Linux 2023 ships the Docker engine but not the Compose
plugin, so `roles/common` fetches the pinned release binary into
`/usr/libexec/docker/cli-plugins/`.
