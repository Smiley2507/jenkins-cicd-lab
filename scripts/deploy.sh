#!/usr/bin/env bash
#
# Runs ON THE APP SERVER. Streamed in over SSH by the Jenkins Deploy stage:
#
#   ssh ec2-user@$APP_HOST "APP_IMAGE=... bash -s" < scripts/deploy.sh
#
# Keeping this in a file rather than a heredoc inside the Jenkinsfile avoids
# a layer of Groovy-inside-shell-inside-SSH quoting, and means you can run it
# by hand when you are debugging a failed deploy.

set -euo pipefail

: "${APP_IMAGE:?APP_IMAGE not set}"
: "${APP_VERSION:?APP_VERSION not set}"
: "${APP_DIR:=/opt/weather-app}"
: "${REGISTRY:=docker.io}"

echo "==> Deploying ${APP_IMAGE} (version ${APP_VERSION}) into ${APP_DIR}"

cd "${APP_DIR}"

if [[ -n "${REGISTRY_USER:-}" && -n "${REGISTRY_PASS:-}" ]]; then
  echo "==> Authenticating to ${REGISTRY}"
  echo "${REGISTRY_PASS}" | docker login "${REGISTRY}" -u "${REGISTRY_USER}" --password-stdin
fi

# Rewrite only the two values Jenkins owns. The compose file itself is managed
# by Ansible and is never touched from here.
echo "==> Writing .env"
cat > .env <<ENVFILE
APP_IMAGE=${APP_IMAGE}
APP_VERSION=${APP_VERSION}
ENVFILE

echo "==> Pulling image"
docker compose pull

echo "==> Starting container"
docker compose up -d --remove-orphans

echo "==> Cleaning up residual containers and images"
docker container prune -f
docker image prune -af --filter "until=1h"

if [[ -n "${REGISTRY_USER:-}" ]]; then
  docker logout "${REGISTRY}" >/dev/null 2>&1 || true
fi

echo "==> Running containers:"
docker compose ps
