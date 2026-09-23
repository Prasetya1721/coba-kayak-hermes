#!/usr/bin/env bash
# =============================================================================
# Hermes Personal AI Agent — production bring-up helper
#
# Usage:
#   ./deploy.sh init          # generate .env, build, start, run migrations
#   ./deploy.sh certs <domain> <email>   # obtain Let's Encrypt certificate
#   ./deploy.sh up            # start prod stack (nginx + certbot)
#   ./deploy.sh logs          # follow logs
#   ./deploy.sh migrate       # run alembic upgrade head
#   ./deploy.sh webhook <token> <secret> # register Telegram webhook
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

compose() { docker compose "$@"; }

cmd_init() {
  if [ ! -f .env ]; then
    cp .env.example .env
    echo ">> Created .env from template. Edit secrets before continuing."
    echo "   Tip: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
  fi
  compose up -d postgres redis
  echo ">> Waiting for Postgres…"; sleep 5
  compose run --rm backend alembic upgrade head
  echo ">> Base services ready."
}

cmd_certs() {
  local domain="${1:?domain required}"
  local email="${2:?email required}"
  mkdir -p docker/nginx/conf.d
  sed "s/\${DOMAIN}/$domain/g" \
    docker/nginx/conf.d/hermes.conf.template \
    > docker/nginx/conf.d/hermes.conf
  compose run --rm --profile prod certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$email" -d "$domain" --agree-tos --no-eff-email
  echo ">> Certificate issued for $domain"
}

cmd_up() { compose --profile prod up -d --build; }
cmd_logs() { compose --profile prod logs -f --tail=200; }
cmd_migrate() { compose run --rm backend alembic upgrade head; }

cmd_webhook() {
  local token="${1:?bot token required}"
  local secret="${2:?webhook secret required}"
  local url="${TELEGRAM_WEBHOOK_URL:?set TELEGRAM_WEBHOOK_URL}"
  curl -fsS "https://api.telegram.org/bot${token}/setWebhook" \
    -d "url=${url}" -d "secret_token=${secret}"
  echo
}

case "${1:-}" in
  init)     cmd_init ;;
  certs)    shift; cmd_certs "$@" ;;
  up)       cmd_up ;;
  logs)     cmd_logs ;;
  migrate)  cmd_migrate ;;
  webhook)  shift; cmd_webhook "$@" ;;
  *)
    echo "Usage: $0 {init|certs <domain> <email>|up|logs|migrate|webhook <token> <secret>}"
    exit 1
    ;;
esac
