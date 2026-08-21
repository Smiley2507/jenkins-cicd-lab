# Runbook — Jenkins CI/CD pipeline for the Weather App

End-to-end procedure: provision infrastructure with Terraform, configure it with
Ansible, wire up Jenkins, run the pipeline, verify, and tear down.

**Region:** eu-west-1 · **AWS profile:** `sandbox-user` · **OS:** Amazon Linux 2023

---

## 0. Architecture

```
                 ┌──────────────────────── VPC 10.20.0.0/16 ─────────────────────────┐
                 │                                                                   │
 you ──22/8080──►│  jenkins-server (t3.medium)         app-server (t3.small)         │
                 │  ├─ Jenkins LTS + Corretto 21       └─ /opt/weather-app           │
                 │  ├─ Docker (builds images) ──22──►     ├─ nginx  :80 ─┐           │
                 │  └─ jenkins user in docker group       └─ web (gunicorn :8000)    │
                 │                                              ▲        │           │
                 └──────────────────────────────────────────────┼────────┼───────────┘
                                                                │        │
 Docker Hub ◄── push ── Jenkins ── pull ────────────────────────┘        │
                                        internet ──80──► nginx ──────────┘
```

Terraform provisions bare instances. Ansible installs and configures everything.
Jenkins builds and ships the application. The three layers don't overlap.

The app container is **not** published to the host — `expose` only. nginx is the
sole ingress, which is why `/nginx-health` and `/health` tell you different
things during a failed deploy: the first proves the proxy is up, the second
proves the app behind it is.

### Repository layout

```
app/         Flask source, templates, tests, requirements, Dockerfile
terraform/   VPC, SGs, key pair, two EC2 instances
ansible/     dynamic EC2 inventory + common / jenkins / appserver roles
nginx/       default.conf — one file, used by both local dev and the server
scripts/     deploy.sh, streamed over SSH by the pipeline
docker-compose.yml   LOCAL development stack (builds from source)
Jenkinsfile          the pipeline
```

There are two compose files and they are not interchangeable. The root one
builds from source for local work. The app server's is templated by Ansible
from `ansible/roles/appserver/templates/docker-compose.yml.j2` and pulls a
published image instead of building.

---

## 1. Prerequisites

On your workstation:

| Tool | Check |
|---|---|
| Terraform ≥ 1.5 | `terraform version` |
| AWS CLI v2 | `aws --version` |
| Ansible ≥ 2.16 | `ansible --version` |
| Python 3 + boto3 | `python3 -c "import boto3; print(boto3.__version__)"` |
| Git | `git --version` |

```bash
pip install boto3 botocore
ansible-galaxy collection install -r ansible/requirements.yml
```

Also needed: a Docker Hub account and a **Personal Access Token**
(Account Settings → Personal access tokens → Generate, Read & Write scope).

---

## 2. Configure the IAM user

1. IAM → Users → your user → **Permissions** → attach `AmazonEC2FullAccess`.
2. **Security credentials** → Create access key → Command Line Interface.

```bash
aws configure --profile sandbox-user
#   Access Key ID     : <paste>
#   Secret Access Key : <paste>
#   Default region    : eu-west-1
#   Default output    : json

aws sts get-caller-identity --profile sandbox-user
```

The ARN must show your new user. If you have `AWS_ACCESS_KEY_ID` exported in
your shell, `unset` it — env vars beat the named profile.

---

## 3. Provision with Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # optional: tighten admin_cidr
terraform init
terraform validate
terraform plan
terraform apply
```

Record the outputs — you need three of them later:

```bash
terraform output                      # everything
terraform output -raw app_private_ip  # → APP_HOST parameter in Jenkins
terraform output -raw app_public_dns  # → the accessibility screenshot
terraform output -raw jenkins_url     # → the Jenkins UI
```

The private key is written to `terraform/cicd-key.pem` with mode 0400.
It is gitignored. **It is also in the Terraform state in plaintext** — never
commit `terraform.tfstate`.

---

## 4. Configure with Ansible

The inventory is dynamic: it queries EC2 for running instances tagged
`Project=jenkins-cicd-lab` and groups them by their `Role` tag.

```bash
cd ../ansible

# Confirm both hosts are discovered before configuring anything.
ansible-inventory --graph
#   @all:
#     |--@role_app:
#     |  |--cicd-app-server
#     |--@role_jenkins:
#     |  |--cicd-jenkins-server

ansible all -m ping        # SSH reachability
ansible-playbook site.yml
```

Run time is 5–8 minutes, mostly `dnf update`. The playbook prints the Jenkins
unlock password and a version block for both hosts — **screenshot that output**,
it satisfies the "tools evidence" requirement in one shot.

If `ansible-inventory --graph` shows nothing, the instances are still booting,
or the profile isn't resolving. Debug with:

```bash
ansible-inventory --list --yaml | head -40
```

---

## 5. Unlock and set up Jenkins

Open `terraform output -raw jenkins_url` (port 8080).

1. Paste the unlock password from the Ansible output. If you missed it:
   `ssh -i terraform/cicd-key.pem ec2-user@<jenkins-ip> "sudo cat /var/lib/jenkins/secrets/initialAdminPassword"`
2. **Install suggested plugins** — this covers Pipeline, Git and Credentials Binding.
3. Create the admin user.
4. Manage Jenkins → Plugins → Available, then install and restart:
   - **Docker Pipeline**
   - **SSH Agent**
   - **JUnit** (usually already present)

---

## 6. Create credentials

Manage Jenkins → Credentials → System → Global credentials → Add.

| ID | Kind | Contents |
|---|---|---|
| `git_credentials` | Username with password | GitHub username + PAT. *Only needed for a private repo.* |
| `registry_creds` | Username with password | Docker Hub username + access token |
| `ec2_ssh` | SSH Username with private key | Username `ec2-user`, key = paste the full contents of `terraform/cicd-key.pem` |

The IDs must match exactly — the Jenkinsfile references them by string.

---

## 7. Set the Docker Hub namespace

The Jenkinsfile builds `${DOCKERHUB_USER}/weather-app`. Set it once, globally:

Manage Jenkins → System → **Global properties** → Environment variables → Add:

```
Name:  DOCKERHUB_USER
Value: <your-dockerhub-username>
```

Alternatively, hardcode `IMAGE_NAME` in the Jenkinsfile's `environment` block.

---

## 8. Create the pipeline job

New Item → name `weather-app-pipeline` → **Pipeline** → OK.

- **Pipeline** → Definition: *Pipeline script from SCM*
- SCM: Git · Repository URL: your app repo
- Credentials: `git_credentials` (leave as *none* for a public repo)
- Branch: `*/main`
- Script Path: `Jenkinsfile`

Save, then **Build with Parameters**:

| Parameter | Value |
|---|---|
| `APP_HOST` | `terraform output -raw app_private_ip` |
| `APP_URL` | `http://` + `terraform output -raw app_public_dns` |

The first build creates the parameters and may fail immediately — that's
normal for a parameterised pipeline. Run it a second time.

---

## 9. What each stage does

| Stage | Action | Fails when |
|---|---|---|
| Checkout | Clones, resolves short commit, sets `IMAGE_TAG=<build>-<sha>` | Bad credentials or branch |
| Install / Build | Creates a venv, installs runtime + dev deps | Dependency resolution fails |
| Test | `pytest` with JUnit XML and coverage | **Any test fails** |
| Docker Build | Builds `app/` with `--build-arg APP_VERSION=${IMAGE_TAG}` | Dockerfile error |
| Push Image | Logs into Docker Hub, pushes `:${IMAGE_TAG}` and `:latest` | Bad `registry_creds` |
| Deploy | SSH to `APP_HOST`, streams `scripts/deploy.sh`, rewrites `.env`, `docker compose up -d` | SSH or pull failure |
| Verify Deployment | Curls `/health`, asserts the reported version **equals this build's tag** | A stale container is still serving |

The verify stage is the interesting one: it doesn't just check that *something*
answers, it checks that the thing answering is the build that just ran. That
catches the classic "deploy succeeded but the old container is still up" failure.

`post { always }` removes the build's images from the controller and prunes
dangling layers, satisfying the cleanup requirement.

---

## 10. Verify

```bash
# The app itself
open http://$(terraform -chdir=terraform output -raw app_public_dns)

# Health endpoint reports the deployed build
curl -s http://$(terraform -chdir=terraform output -raw app_public_dns)/health
# {"status":"ok","version":"7-a1b2c3d"}

# Proxy liveness, answered by nginx without touching the app
curl -s http://$(terraform -chdir=terraform output -raw app_public_dns)/nginx-health
# nginx ok
```

Select a city, submit, confirm live temperature and AQI render.

**Screenshots to capture for submission:**

1. Ansible output showing Jenkins / Java / Docker / Compose / OS versions (both hosts)
2. Jenkins Stage View — all seven stages green
3. Console log of the Push stage showing the digest
4. Console log of Verify Deployment showing `Deployed version: N-sha`
5. Test result trend / JUnit report page
6. The app in a browser at the EC2 public DNS
7. `curl /health` output matching the build number

---

## 11. Troubleshooting

**`docker: permission denied` in the Docker Build stage**
The `jenkins` user's docker group membership needs a service restart:
```bash
sudo usermod -aG docker jenkins && sudo systemctl restart jenkins
```

**Deploy hangs, or `Host key verification failed`**
The jenkins user hasn't trusted the app server. The Ansible role pre-populates
`known_hosts`, but if it was skipped:
```bash
sudo -u jenkins ssh-keyscan -H <app-private-ip> >> /var/lib/jenkins/.ssh/known_hosts
```

**`Permission denied (publickey)` on deploy**
`ec2_ssh` holds the wrong key, or the username isn't `ec2-user`. Verify by hand
from the controller with the same key.

**Verify Deployment fails with an old version string**
The pull returned a cached image. Confirm the tag actually pushed:
`docker manifest inspect <user>/weather-app:<tag>`

**`502 Bad Gateway` from nginx**
nginx is up but gunicorn isn't. The compose file gates nginx on the app's
healthcheck, so this usually means the app container is crash-looping:
```bash
cd /opt/weather-app && docker compose ps && docker compose logs web --tail 50
```

**nginx config change didn't take effect**
`/opt/weather-app/nginx/default.conf` is overwritten by Ansible on every run.
Edit `nginx/default.conf` in the repo and re-run `ansible-playbook site.yml` —
the handler reloads nginx in place. To check syntax before deploying:
```bash
docker run --rm -v "$PWD/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.27-alpine nginx -t
```

**Build runs out of disk on the controller**
```bash
docker system prune -af --volumes
```
Or raise `jenkins_root_volume_size` and re-apply.

**Ansible can't find hosts**
Instances must be `running` and tagged `Project=jenkins-cicd-lab`. Check with
`aws ec2 describe-instances --profile sandbox-user --filters Name=tag:Project,Values=jenkins-cicd-lab --query 'Reservations[].Instances[].[Tags[?Key==`Name`].Value|[0],State.Name]' --output table`

---

## 12. Teardown

```bash
cd terraform
terraform destroy
```

Then delete the Docker Hub repository if you don't want the images kept, and
deactivate the IAM access key.

Leaving this running costs roughly **$45/month** plus EBS. Destroy it between
sessions — `terraform apply` rebuilds it in about three minutes, and
`ansible-playbook site.yml` reconfigures it in eight.
