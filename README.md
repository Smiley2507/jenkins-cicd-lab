# Weather App — Jenkins CI/CD Pipeline

A small Flask service that reports current conditions and air quality for a
scoped list of cities, built and deployed by a Jenkins pipeline onto an EC2
host behind nginx.

The application is deliberately modest. The point of this repository is the
pipeline around it.

## Layout

```
app/                  Flask source, templates, tests, requirements, Dockerfile
terraform/            VPC, subnet, IGW, route table, SGs, key pair, 2× EC2
ansible/              dynamic EC2 inventory + common / jenkins / appserver roles
nginx/default.conf    reverse proxy config — one file, local dev and prod
scripts/deploy.sh     runs on the app server, streamed in over SSH
docker-compose.yml    LOCAL dev stack (builds from source)
Jenkinsfile           the pipeline
runbook.md            full procedure, IAM user through teardown
```

## The app

`GET /` renders a form with six allowlisted cities. `POST /` looks the city up
against [Open-Meteo](https://open-meteo.com/) (no API key required) and renders
temperature, humidity, wind, conditions and a banded European AQI value.
`GET /health` returns `{"status": "ok", "version": "<build tag>"}`.

The split between `app.py` and `weather.py` is what makes the test suite
meaningful: network logic is tested by monkeypatching `requests.get`, routes
through Flask's test client. CI never depends on Open-Meteo being up.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt -r app/requirements-dev.txt
pytest                          # 35 passing
```

The full stack, nginx included, mirroring production topology:

```bash
docker compose up --build       # http://localhost:8080

# or the image on its own
docker build -t weather-app:local --build-arg APP_VERSION=local app/
```

## Serving

nginx is the only ingress. The app container is `expose`d, never published, so
nothing reaches gunicorn except through the proxy:

```
internet :80 ──► nginx ──► web:8000 (gunicorn, 2 workers)
```

`/nginx-health` is answered by nginx itself and `/health` by the app, so a
failed deploy tells you which half broke.

## The pipeline

Declarative, seven stages:

**Checkout** → **Install / Build** → **Test** → **Docker Build** →
**Push Image** → **Deploy** → **Verify Deployment**

Every image is tagged `${BUILD_NUMBER}-${SHORT_COMMIT}` and that tag is baked
into the container as `APP_VERSION`. The final stage curls `/health` on the
deployed host and asserts the version it reports matches the tag this build
produced — so a deploy that silently left a stale container running fails the
build instead of passing it.

Credentials consumed: `git_credentials` (private repos only), `registry_creds`
(Docker Hub), `ec2_ssh` (deploy key).

## Infrastructure

Terraform provisions bare instances — no `user_data` anywhere. Ansible installs
and configures. Jenkins builds and ships. The three layers don't overlap, and
that boundary is deliberate: Ansible never ships application code, and Jenkins
never edits machine configuration.

`terraform/` composes
[terraform-aws-modules](https://github.com/Smiley2507/terraform-aws-modules)
unmodified. `ansible/` discovers hosts dynamically from the `Role` tag that
Terraform sets, so there is no static inventory to keep in sync.

## Getting started

See **[runbook.md](runbook.md)**.

## Cleanup

`terraform destroy` in `terraform/`. The pipeline prunes controller-side images
after every build; a daily cron prunes the app server.
