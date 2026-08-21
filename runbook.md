# Runbook 
A step-by-step guide to reproducing the whole project: two EC2 instances, a
configured Jenkins controller, and a working pipeline that deploys the app.

Every phase ends with a **checkpoint** — something to run or look at that tells
you it worked before you move on. If a checkpoint fails, stop there; the next
phase depends on it.

| | |
|---|---|
| **Time** | ~45 minutes end to end, of which ~12 is waiting |
| **Cost** | ~$25/month if left running. Destroy it between sessions (Phase 9) |
| **Region** | eu-west-1 |
| **OS** | Amazon Linux 2023 |

### Contents

- [Phase 0 — Prerequisites](#phase-0--prerequisites)
- [Phase 1 — Accounts and credentials](#phase-1--accounts-and-credentials)
- [Phase 2 — Provision the infrastructure](#phase-2--provision-the-infrastructure)
- [Phase 3 — Configure the servers](#phase-3--configure-the-servers)
- [Phase 4 — Set up Jenkins](#phase-4--set-up-jenkins)
- [Phase 5 — Create and run the pipeline](#phase-5--create-and-run-the-pipeline)
- [Phase 6 — Verify the deployment](#phase-6--verify-the-deployment)
- [Phase 7 — Enable the push trigger (optional)](#phase-7--enable-the-push-trigger-optional)
- [Phase 8 — Capture evidence](#phase-8--capture-evidence)
- [Phase 9 — Tear it down](#phase-9--tear-it-down)
- [Appendix A — Troubleshooting](#appendix-a--troubleshooting)
- [Appendix B — Reference](#appendix-b--reference)

---

## Phase 0 — Prerequisites

### What you need before starting

| Requirement | Why |
|---|---|
| AWS account with IAM access | Terraform creates the infrastructure |
| Docker Hub account | The registry the pipeline pushes to |
| GitHub account | Jenkins clones the pipeline from here |
| A Linux/macOS/WSL shell | Everything below assumes bash |

### Install the tooling

```bash
terraform version     # need >= 1.5
aws --version         # need v2
git --version
python3 --version     # need >= 3.9
```

Ansible needs `boto3` importable **by the same Python that runs Ansible**, which
is the single most common setup mistake. Install both together:

```bash
python3 -m venv ~/.venvs/ansible
source ~/.venvs/ansible/bin/activate
pip install --upgrade pip
pip install ansible boto3 botocore
```

Or with pipx, which avoids having to activate anything later:

```bash
pipx install --include-deps ansible
pipx inject ansible boto3 botocore
```

### ✅ Checkpoint 0

```bash
which ansible                                  # inside your venv or pipx path
python -c "import boto3; print(boto3.__version__)"
ansible --version | tail -2                    # note the python version line
```

All three must succeed. If `ansible` resolves to `/usr/bin/ansible` while boto3
lives in your venv, they are different interpreters and Phase 3 will fail.

> **Remember:** if you used a venv, you must `source ~/.venvs/ansible/bin/activate`
> in every new shell before running Ansible.

---

## Phase 1 — Accounts and credentials

### 1.1 Get the code

```bash
git clone https://github.com/<you>/jenkins-cicd-lab.git
cd jenkins-cicd-lab
```

If you're starting from the project files rather than a clone, push them first —
Jenkins pulls the pipeline from GitHub, so the repo has to exist:

```bash
git init && git add . && git commit -m "CI/CD lab"
git branch -M main
git remote add origin https://github.com/<you>/jenkins-cicd-lab.git
git push -u origin main
```

### 1.2 Create a Docker Hub access token

Docker Hub → your avatar → **Account settings** → **Personal access tokens** →
**Generate new token**. Permissions: **Read & Write**.

**Copy it now.** Docker Hub shows it once. You'll paste it in Phase 4.

Use a token rather than your account password — it's scoped, revocable, and
doesn't unlock your account if it leaks.

### 1.3 Configure the AWS profile

In the AWS console: **IAM → Users →** your user.

1. **Permissions** → attach `AmazonEC2FullAccess`. (Add `AmazonS3FullAccess`
   too if you plan to use the S3 remote backend.)
2. **Security credentials** → **Create access key** → *Command Line Interface*.

Then locally:

```bash
aws configure --profile sandbox-user
#   AWS Access Key ID     : <paste>
#   AWS Secret Access Key : <paste>
#   Default region name   : eu-west-1
#   Default output format : json
```

Clear any inherited environment variables — they silently override the profile:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
```

### ✅ Checkpoint 1

```bash
aws sts get-caller-identity --profile sandbox-user
```

The `Arn` must end in **your** IAM user's name. If it shows a different user or
a role, an environment variable or a different profile is winning.

---

## Phase 2 — Provision the infrastructure

Terraform creates the network, security groups, an SSH key pair, and two EC2
instances. It installs **no software** — that's Phase 3.

### 2.1 Review what you're about to create

```bash
cd terraform
terraform init
terraform validate
terraform plan
```

Read the plan. You should see roughly **18 resources to add** and nothing to
destroy. Notable defaults, all overridable in `terraform.tfvars`:

| Variable | Default | Meaning |
|---|---|---|
| `jenkins_instance_type` | `t3.small` | Controller. See the note below |
| `app_instance_type` | `t3.micro` | Deploy target |
| `vpc_cidr` | `10.20.0.0/16` | Network range |
| `admin_cidr` | `0.0.0.0/0` | Who may reach SSH and Jenkins' UI |
| `ami_name_filter` | `al2023-ami-2023.*-kernel-6.1-x86_64` | Pinned deliberately — see Appendix A |

> **On `admin_cidr`:** the default exposes port 8080 to the internet, which is
> what makes GitHub webhooks possible (Phase 7). To lock it down instead, set
> `admin_cidr = "<your-ip>/32"` in `terraform.tfvars` — but then webhooks won't
> reach Jenkins and you'll need polling.

### 2.2 Apply

```bash
terraform apply       # review, then type: yes
```

Takes about three minutes. Most of that is EC2 instances booting.

### 2.3 Record the outputs

You'll need three values repeatedly. Keep this terminal open, or note them down:

```bash
terraform output -raw jenkins_url         # e.g. http://54.x.x.x:8080
terraform output -raw app_private_ip      # e.g. 10.20.1.14   ← APP_HOST
terraform output -raw app_public_dns      # where the app will appear
```

Terraform also wrote the SSH private key to `terraform/cicd-key.pem` at mode
0400. That one key does three jobs: your own SSH access, Ansible's connection,
and Jenkins' `ec2_ssh` credential.

> **Security note:** this key is stored in the Terraform state in plaintext.
> Never commit `terraform.tfstate` — `.gitignore` already excludes it, along
> with `*.pem`.

### ✅ Checkpoint 2

```bash
terraform output                                    # all values populated
ssh -i cicd-key.pem ec2-user@$(terraform output -raw jenkins_public_ip) 'hostname'
```

The SSH command should print a hostname. If it's refused, the instance is still
booting — wait 30 seconds. If it says `Permissions 0644 are too open`, run
`chmod 400 cicd-key.pem`.

Run `terraform plan` once more: it should report **no changes**. That's your
proof the configuration is stable, not merely lucky.

---

## Phase 3 — Configure the servers

Ansible installs everything: Docker and Compose on both hosts, plus Java and
Jenkins on the controller. It finds the hosts by querying EC2 — there's no
inventory file to keep in sync.

### 3.1 Install the collections

```bash
cd ../ansible
ansible-galaxy collection install -r requirements.yml
```

### 3.2 Confirm host discovery *before* configuring anything

```bash
ansible-inventory --graph
```

Expected:

```
@all:
  |--@ungrouped:
  |--@aws_ec2:
  |  |--cicd-app-server
  |  |--cicd-jenkins-server
  |--@role_app:
  |  |--cicd-app-server
  |--@role_jenkins:
  |  |--cicd-jenkins-server
```

Those `role_*` groups come from the `Role` tag Terraform set. They are the
entire interface between Terraform and Ansible — if they're missing, the
playbook has nothing to target.

Empty output usually means the instances are still booting, or the AWS profile
isn't resolving. Retry after 30 seconds, then see Appendix A.

```bash
ansible all -m ping        # expect two "pong" responses
```

### 3.3 Run the playbook

```bash
ansible-playbook site.yml
```

Five to eight minutes; most of it is `dnf update` and the Docker engine install.
You'll see three plays run in order: `common` on both hosts, then `jenkins` on
the controller, then `appserver` on the target.

**Two things in the output matter. Capture them now.**

1. The **Jenkins unlock password**, printed by the *Show the initial admin
   password* task. You need it in Phase 4.
2. The **version block** — Jenkins, Java, Docker, Compose, and OS for both
   hosts. Screenshot this: it's your "tools evidence" deliverable in one shot.

If you lose the password:

```bash
ssh -i ../terraform/cicd-key.pem ec2-user@<jenkins-ip> \
  "sudo cat /var/lib/jenkins/secrets/initialAdminPassword"
```

### ✅ Checkpoint 3

The play recap should show `failed=0` for both hosts. Then:

```bash
curl -sI http://$(cd ../terraform && terraform output -raw jenkins_public_ip):8080/login | head -1
# HTTP/1.1 200 OK   (or 403 — both mean Jenkins is answering)
```

Re-running `ansible-playbook site.yml` should now report almost all `ok` and few
`changed`. That idempotency is the point of using Ansible over `user_data`.

---

## Phase 4 — Set up Jenkins

This phase is all browser work. Open the `jenkins_url` from Phase 2.

### 4.1 Unlock and initialise

1. Paste the unlock password from Phase 3.
2. Choose **Install suggested plugins**. This gives you Pipeline, Git,
   Credentials Binding, JUnit and the GitHub plugin. Wait for it to finish.
3. Create your admin user. **Save these credentials** — the setup wizard does
   not show them again.
4. Accept the default Jenkins URL.

### 4.2 Add the two remaining plugins

**Manage Jenkins → Plugins → Available plugins**, search for and install:

- **Docker Pipeline**
- **SSH Agent**

Tick *Restart Jenkins when installation is complete*. Wait for it to come back.

### 4.3 Create the credentials

**Manage Jenkins → Credentials → System → Global credentials → + Add Credentials**

**Docker Hub:**

| Field | Value |
|---|---|
| Kind | Username with password |
| Username | your Docker Hub username |
| Password | the token from step 1.2 |
| ID | **`registry_creds`** |

**The EC2 deploy key:**

| Field | Value |
|---|---|
| Kind | SSH Username with private key |
| ID | **`ec2_ssh`** |
| Username | `ec2-user` |
| Private Key | *Enter directly* → paste the entire contents of `terraform/cicd-key.pem` |

Include the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END-----` lines.

> A third credential, `git_credentials` (username + GitHub PAT), is only needed
> if your repository is **private**.

**The IDs must match exactly.** The Jenkinsfile looks them up by string; a typo
here surfaces four stages later as a confusing failure.

### ✅ Checkpoint 4

The credentials list shows `registry_creds` and `ec2_ssh`. **Manage Jenkins →
Nodes** shows the Built-In Node online with at least 1 executor.

If the node is offline or shows 0 executors, fix it now — see Appendix A,
*"Jenkins never schedules a build"*. A queued build that never starts is the
most confusing failure in this whole runbook, and it's entirely preventable at
this point.

---

## Phase 5 — Create and run the pipeline

### 5.1 Create the job

**New Item** → name it `weather-app-pipeline` → choose **Pipeline** → OK.

Scroll to the **Pipeline** section at the bottom:

| Field | Value |
|---|---|
| Definition | **Pipeline script from SCM** |
| SCM | Git |
| Repository URL | `https://github.com/<you>/jenkins-cicd-lab.git` |
| Credentials | *none* (or `git_credentials` if private) |
| Branch Specifier | `*/main` |
| Script Path | `Jenkinsfile` |

**Save.**

### 5.2 The first build will fail. This is expected.

Click **Build Now**. It fails almost immediately.

Jenkins doesn't know the pipeline has parameters until it has read the
Jenkinsfile once — so build #1 runs with none, and the guard in the Checkout
stage stops it with a clear message. This happens to everyone exactly once.

### 5.3 The real build

The left menu now offers **Build with Parameters**:

| Parameter | Value |
|---|---|
| `DOCKERHUB_USER` | your Docker Hub username (lowercase) |
| `APP_HOST` | the `app_private_ip` from Phase 2 |
| `APP_URL` | `http://` + the `app_public_dns` from Phase 2 |

Click **Build**. Two to four minutes.

### 5.4 Watch it work

Open the build → **Console Output**, or use the Stage View on the job page.

| Stage | What you should see |
|---|---|
| Checkout | The commit hash and message |
| Install / Build | pip resolving Flask, requests, gunicorn, pytest |
| Test | `35 passed` |
| Docker Build | Layer-by-layer build, then the image ID |
| Push Image | `docker login` succeeding, then the pushed digest |
| Deploy | SSH connecting, `docker compose pull`, containers starting, then a JSON health response |

### ✅ Checkpoint 5

All stages green, and the Deploy stage's output ends with a health response
whose `version` equals this build's number.

If a stage fails, jump to Appendix A — the common causes are all listed, and
`docker: permission denied` in Docker Build is the single most likely one.

---

## Phase 6 — Verify the deployment

Don't trust the pipeline's own word for it. Check from outside.

```bash
cd ../terraform
APP=$(terraform output -raw app_public_dns)

curl -s  http://$APP/health          # {"status":"ok","version":"2"}
curl -s  http://$APP/nginx-health    # nginx ok
curl -sI http://$APP/ | head -1      # HTTP/1.1 200 OK
```

Then open `http://$APP` in a browser, choose a city, and submit. You should get
live temperature, humidity, wind, conditions and an air-quality band.

### ✅ Checkpoint 6

Three things must all be true:

1. The page renders **live weather** — proving the app reaches Open-Meteo.
2. `/health` returns a `version` **equal to the Jenkins build number** —
   proving the running container is the one that build produced, not a
   leftover.
3. `/nginx-health` answers — proving the proxy layer is doing its job.

If `/nginx-health` answers but `/health` gives a 502, the proxy is up and the
app behind it is not. That's exactly what the two endpoints exist to tell you
apart.

---

## Phase 7 — Enable the push trigger (optional)

Everything so far has been manual. This makes a `git push` build and deploy on
its own. It's not required by the lab, but it's what makes the pipeline
genuinely *continuous*.

### 7.1 Give the parameters real defaults

A webhook can't fill in a form, so a triggered build uses each parameter's
`defaultValue`. In `Jenkinsfile`:

```groovy
string(name: 'DOCKERHUB_USER', defaultValue: 'your-dockerhub-username', ...)
string(name: 'APP_HOST',       defaultValue: '10.20.1.14',              ...)
```

Commit and push, then **run one manual build** so Jenkins reads the `triggers`
block — same chicken-and-egg as parameters.

### 7.2 Enable it in the job

Job → **Configure** → **Build Triggers** → tick **GitHub hook trigger for GITScm
polling** → Save.

The `triggers { githubPush() }` block in the Jenkinsfile declares the same
thing. Having both is harmless, and the checkbox is easier to screenshot.

### 7.3 Add the webhook on GitHub

Repo → **Settings** → **Webhooks** → **Add webhook**:

| Field | Value |
|---|---|
| Payload URL | `http://<jenkins-public-ip>:8080/github-webhook/` |
| Content type | `application/json` |
| Secret | leave empty |
| Events | *Just the push event* |
| Active | ticked |

The **trailing slash** on `/github-webhook/` is required.

### ✅ Checkpoint 7

```bash
git commit --allow-empty -m "test: webhook trigger"
git push
```

A build starts within a couple of seconds, and its console log opens with
**"Started by GitHub push by &lt;you&gt;"**. On GitHub, **Settings → Webhooks →
your webhook → Recent Deliveries** shows the POST with a green tick and HTTP 200.

> **If the webhook can't reach Jenkins:** it needs port 8080 open to the
> internet. If you tightened `admin_cidr`, either allow GitHub's hook IP ranges
> (published at <https://api.github.com/meta>) or switch to polling — comment
> out `githubPush()` and uncomment `pollSCM('H/5 * * * *')`. Polling needs no
> inbound access at all, at the cost of up to five minutes of latency.

---

## Phase 8 — Capture evidence

Do this **while everything is still running.** The environment is one
`terraform destroy` away from gone, and screenshots can't be reconstructed.

| # | File | What to capture |
|---|---|---|
| 1 | `01-tool-versions.png` | The version block from Phase 3 — both hosts |
| 2 | `02-credentials.png` | Manage Jenkins → Credentials, showing both IDs |
| 3 | `03-stage-view.png` | Stage View, all stages green |
| 4 | `04-test-results.png` | The JUnit page, 35 passing |
| 5 | `05-push-image.png` | Push Image console output with the digest |
| 6 | `06-deploy.png` | Deploy console output with the health response |
| 7 | `07-app-live.png` | Browser at the public DNS, live weather rendered |
| 8 | `08-health.png` | `curl /health` with the version matching the build |
| 9 | `09-terraform-plan.png` | `terraform plan` reporting no changes |
| 10 | `10-trigger.png` | Console header: "Started by GitHub push" *(if Phase 7)* |
| 11 | `11-webhook.png` | GitHub Recent Deliveries, HTTP 200 *(if Phase 7)* |

Save them in `screenshots/` under exactly these names — the README references
them by filename.

Two tips: pick **Kigali** for #7, since live local weather is more convincing
than London. And take #7 and #8 in the same session so the version numbers
visibly agree.

---

## Phase 9 — Tear it down

```bash
cd terraform
terraform destroy      # type: yes
```

Takes about two minutes. Then, optionally: delete the Docker Hub repository,
and deactivate the IAM access key you created in Phase 1.

Rebuilding is `terraform apply` (3 min) plus `ansible-playbook site.yml` (8
min). Jenkins itself is *not* restored — you'd redo Phase 4, since the unlock,
plugins and credentials live on the instance's disk rather than in code.

> That's a real limitation worth naming if anyone asks: the infrastructure and
> host configuration are code, but the Jenkins controller's own configuration is
> not. Making it so is what Jenkins Configuration as Code (JCasC) is for.

---

## Appendix A — Troubleshooting

### Jenkins never schedules a build

Symptom: the build sits in the queue, *"Waiting for next available executor"*.

Cause is almost always one of three. Hover over the queued item — Jenkins states
the reason in plain words.

**Node offline for temp space.** Amazon Linux 2023 mounts `/tmp` as a tmpfs
sized at 50% of RAM. On a 2 GB instance that's ~956 MiB, below Jenkins'
hardcoded 1 GiB threshold, so it takes the node offline even though nothing is
full. Fix immediately via **Manage Jenkins → Nodes → ⚙ → Configure Monitors →
Free Temp Space** → set `512MiB`. The permanent fix is in the Ansible `jenkins`
role, which points `java.io.tmpdir` at the EBS volume.

**Zero executors.** **Manage Jenkins → Nodes → Built-In Node → Configure →
Number of executors** must be at least 1.

**A previous build is still holding it.** Abort any build still listed as
running.

### `docker: permission denied` in Docker Build

The `jenkins` user's `docker` group membership doesn't apply until the service
restarts:

```bash
sudo usermod -aG docker jenkins && sudo systemctl restart jenkins
```

### `Permission denied (publickey)` in Deploy

The `ec2_ssh` credential has the wrong key or username. The username must be
`ec2-user`. Test the same key by hand from the controller.

### Deploy hangs, or `Host key verification failed`

The `jenkins` user hasn't trusted the app server's host key:

```bash
sudo -u jenkins ssh-keyscan -H <app-private-ip> >> /var/lib/jenkins/.ssh/known_hosts
```

The Ansible `jenkins` role does this for you. Note the scan must run **on the
Jenkins host** — an `ssh-keyscan` from your laptop can't reach a private VPC IP.

### `denied: requested access to the resource is denied` on push

`DOCKERHUB_USER` doesn't match the account that owns `registry_creds`. Also
check for capitals — Docker Hub rejects uppercase repository names, which is why
the pipeline lowercases the value.

### `502 Bad Gateway` from the app

nginx is up, gunicorn isn't. On the app server:

```bash
cd /opt/weather-app && docker compose ps && docker compose logs web --tail 50
```

### `Could not open requirements file`

`app/requirements-dev.txt` isn't committed. Check `git ls-files app/`.

### Hundreds of lines of `Depsolve Error ... conflicts with curl`

`curl` was requested on AL2023, which ships `curl-minimal` and won't erase it
implicitly. Remove `curl` from `common_packages` — the minimal package already
provides `/usr/bin/curl`.

### `Volume of size 20GB is smaller than snapshot`

The AMI filter matched a specialised variant — the ECS/Neuron images carry 30 GB
snapshots. `ami_name_filter` is pinned to `al2023-ami-2023.*-kernel-6.1-x86_64`
for exactly this reason; check it hasn't been loosened. To see what resolved:

```bash
aws ec2 describe-images --profile sandbox-user --region eu-west-1 --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023.*-kernel-6.1-x86_64" \
  --query 'sort_by(Images,&CreationDate)[-1].[ImageId,Name,BlockDeviceMappings[0].Ebs.VolumeSize]' \
  --output table
```

### `ansible-inventory --graph` shows nothing

Instances must be **running** and tagged `Project=jenkins-cicd-lab`:

```bash
aws ec2 describe-instances --profile sandbox-user --region eu-west-1 \
  --filters "Name=tag:Project,Values=jenkins-cicd-lab" \
  --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output table
```

Also confirm `profile: sandbox-user` in `inventory.aws_ec2.yml` matches your
configured profile name.

### Ansible: `No module named 'ansible_collections.amazon'`

The collections aren't installed for this Ansible:

```bash
ansible-galaxy collection install -r requirements.yml --force
```

### Ansible: callback plugin errors, or `tags` deprecation warnings

`community.general.yaml` was removed in v12 — use `stdout_callback = default`
with `callback_result_format = yaml`. The `tags` warning comes from the
`amazon.aws` plugin itself and is harmless; your `keyed_groups` should use
`ec2_tags.Role`.

### nginx config changes don't take effect

`/opt/weather-app/nginx/default.conf` is overwritten by Ansible on every run.
Edit `nginx/default.conf` in the repo and re-run the playbook. To check syntax
before deploying:

```bash
docker run --rm -v "$PWD/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.27-alpine nginx -t
```

### Controller out of disk

```bash
docker system prune -af --volumes
```

Or raise `jenkins_root_volume_size` and re-apply.

---

## Appendix B — Reference

### Ports

| Port | Host | Open to |
|---|---|---|
| 22 | both | `admin_cidr`; app server also from the VPC CIDR |
| 8080 | jenkins-server | `admin_cidr` — the Jenkins UI, and GitHub webhooks |
| 80 | app-server | `0.0.0.0/0` — the application via nginx |
| 8000 | app-server | container-internal only, never published |

### Jenkins credential IDs

| ID | Kind | Used by |
|---|---|---|
| `registry_creds` | Username with password | Push Image, Deploy |
| `ec2_ssh` | SSH username with private key | Deploy |
| `git_credentials` | Username with password | Checkout (private repos only) |

### Key file locations

| Path | What |
|---|---|
| `terraform/cicd-key.pem` | Generated SSH private key, mode 0400 |
| `/opt/weather-app/` | App directory on the deploy target |
| `/opt/weather-app/.env` | The only file Jenkins rewrites on deploy |
| `/opt/weather-app/docker-compose.yml` | Templated by Ansible — don't edit on the host |
| `/var/lib/jenkins/` | Jenkins home on the controller |

### Useful commands

```bash
# Infrastructure
terraform output                              # all values
terraform plan                                # should say "no changes"

# Configuration
ansible-inventory --graph                     # what Ansible can see
ansible all -m ping                           # connectivity
ansible-playbook site.yml --check             # dry run

# On the app server
docker compose ps                             # in /opt/weather-app
docker compose logs web --tail 50
cat .env                                      # which image is deployed

# On the Jenkins controller
sudo systemctl status jenkins
sudo journalctl -u jenkins -n 50
df -h /var/lib/jenkins
```
