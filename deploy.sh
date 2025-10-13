#!/usr/bin/env bash
set -Eeuo pipefail

### --- Config (override at runtime: BRANCH=main bash deploy.sh) ---
APP_DIR="/srv/sakarela/app"
VENV_DIR="/srv/sakarela/venv"
SERVICE="${SERVICE:-sakarela}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"
EXPECTED_REMOTE_URL="${EXPECTED_REMOTE_URL:-git@github-sakarela-ro:rainballs/Sakarela.git}"
DJANGO_SETTINGS="${DJANGO_SETTINGS:-Sakarela_DJANGO.settings}"
RUN_AS="${RUN_AS:-www-data}"
PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
umask 022

log(){ printf "\n[%s] %s\n" "$(date +'%F %T')" "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

# Ensure Git won't block due to ownership (idempotent)
git config --global --add safe.directory "$APP_DIR" >/dev/null 2>&1 || true

cd "$APP_DIR" || die "APP_DIR not found: $APP_DIR"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "Not a git repo: $APP_DIR"
fi

log "1/7 Git fetch/reset (branch: $BRANCH)"
cur="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
if [ "$cur" != "$EXPECTED_REMOTE_URL" ]; then
  log "Setting remote $REMOTE -> $EXPECTED_REMOTE_URL"
  git remote set-url "$REMOTE" "$EXPECTED_REMOTE_URL"
fi
command -v git-lfs >/dev/null 2>&1 && git lfs install >/dev/null 2>&1 || true
git fetch --all --prune
git reset --hard "${REMOTE}/${BRANCH}"
command -v git-lfs >/dev/null 2>&1 && git lfs pull || true

log "2/7 Ensure venv + deps"
if [ ! -x "${VENV_DIR}/bin/activate" ]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
$PIP install --upgrade pip wheel >/dev/null
[ -f requirements.txt ] && $PIP install -r requirements.txt

log "3/7 Django check/migrate/collectstatic"
export DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS"
set -a; [ -f .env ] && . ./.env; set +a
$PY manage.py check
$PY manage.py migrate --noinput
$PY manage.py collectstatic --noinput

# detect static dir (prefer staticfiles, else static_root)
STATIC_DIR=""
[ -d "${APP_DIR}/staticfiles" ] && STATIC_DIR="${APP_DIR}/staticfiles"
[ -z "$STATIC_DIR" ] && [ -d "${APP_DIR}/static_root" ] && STATIC_DIR="${APP_DIR}/static_root"

log "4/7 Permissions"
[ -n "$STATIC_DIR" ] && [ -d "$STATIC_DIR" ] && chown -R "$RUN_AS:$RUN_AS" "$STATIC_DIR" || true
[ -f "${APP_DIR}/db.sqlite3" ] && chown "$RUN_AS:$RUN_AS" "${APP_DIR}/db.sqlite3" || true

log "5/7 Restart service: $SERVICE"
systemctl restart "$SERVICE"
sleep 1
systemctl --no-pager --lines=25 status "$SERVICE" || true

log "6/7 Health checks"
if curl -fsS -H 'Host: dev.sakarela.com' http://127.0.0.1:8000/ -o /dev/null; then
  echo "Upstream OK (127.0.0.1:8000)"
else
  echo "Upstream check FAILED"
fi
if [ -n "$STATIC_DIR" ]; then
  echo "STATIC at: $STATIC_DIR"
  ls -ld "$STATIC_DIR" || true
else
  echo "STATIC DIR unknown (check Django STATIC_ROOT)."
fi

log "7/7 Done."
