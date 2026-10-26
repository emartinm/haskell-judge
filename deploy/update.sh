#!/bin/bash
# Updates the judge in production to the latest version of the repository. Same layout as
# manage.sh (<base>/app, <base>/venv, <base>/env). Run it as root:
#   sudo <base>/app/deploy/update.sh            # only if there are new commits
#   sudo <base>/app/deploy/update.sh --force    # even if there are none
# Steps: git pull, pip install (only if requirements.txt changed), migrate, collectstatic,
# check --deploy, restart of the service and a request to the login page through gunicorn.
# The application steps run as the owner of <base>/app. JUDGE_BASE sets <base> when the
# script is run from another place (sudo JUDGE_BASE=<base> ./update.sh); SERVICE overrides
# the name of the systemd service (haskell-judge by default).
set -euo pipefail

BASE=${JUDGE_BASE:-$(cd "$(dirname "$0")/../.." && pwd)}
APP="$BASE/app"
SERVICE=${SERVICE:-haskell-judge}
FORCE=${1:-}

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "ejecútalo con sudo"
[ -d "$APP/.git" ] && [ -f "$BASE/env" ] || fail "no hay un juez instalado en $BASE (falta $APP o $BASE/env).
Ejecuta el script desde <base>/app/deploy/ o indica la instalación: sudo JUDGE_BASE=<base> $0"
OWNER=$(stat -c %U "$APP")
as_owner() { sudo -u "$OWNER" "$@"; }
manage() { as_owner "$APP/deploy/manage.sh" "$@"; }
env_value() { sed -n "s/^$1=//p" "$BASE/env" | tail -n 1; }

step "Descargando cambios"
OLD=$(as_owner git -C "$APP" rev-parse HEAD)
as_owner git -C "$APP" pull --ff-only
NEW=$(as_owner git -C "$APP" rev-parse HEAD)
if [ "$OLD" = "$NEW" ]; then
    echo "No hay commits nuevos."
    [ "$FORCE" = "--force" ] || { echo "Nada que hacer (usa --force para repetir los pasos)."; exit 0; }
else
    as_owner git -C "$APP" log --oneline "$OLD..$NEW"
fi

if ! as_owner git -C "$APP" diff --quiet "$OLD" "$NEW" -- requirements.txt; then
    step "Instalando dependencias (requirements.txt ha cambiado)"
    as_owner "$BASE/venv/bin/pip" install -r "$APP/requirements.txt"
fi

step "Migraciones"
manage migrate --noinput

step "Ficheros estáticos"
manage collectstatic --noinput

step "Comprobación de la configuración"
manage check --deploy

step "Reiniciando $SERVICE"
systemctl restart "$SERVICE"
for _ in $(seq 1 20); do
    systemctl is-active --quiet "$SERVICE" && break
    sleep 1
done
systemctl is-active --quiet "$SERVICE" || {
    journalctl -u "$SERVICE" -n 30 --no-pager
    fail "$SERVICE no ha arrancado"
}

step "Comprobando la página de entrada"
HOST=$(env_value ALLOWED_HOSTS | cut -d, -f1)
BIND=$(env_value GUNICORN_BIND)
# Directly to gunicorn: without the header that nginx adds, the judge redirects to HTTPS
for _ in $(seq 1 20); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $HOST" -H "X-Forwarded-Proto: https" \
        "http://$BIND/haskell/login/" || true)
    [ "$CODE" = 200 ] && break
    sleep 1
done
[ "$CODE" = 200 ] || {
    journalctl -u "$SERVICE" -n 30 --no-pager
    fail "la página de entrada responde $CODE"
}
echo "OK: https://$HOST/haskell/ responde (versión $(as_owner git -C "$APP" log -1 --format='%h %s'))"
