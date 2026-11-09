#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -z "${PG_BIN:-}" ]]; then
 for candidate in /opt/homebrew/opt/postgresql@17/bin /usr/local/opt/postgresql@17/bin /usr/lib/postgresql/17/bin; do
  if [[ -x "$candidate/pg_ctl" ]]; then PG_BIN="$candidate"; break; fi
 done
fi
if [[ -z "${PG_BIN:-}" ]] && command -v pg_ctl >/dev/null; then PG_BIN="$(dirname "$(command -v pg_ctl)")"; fi
[[ -x "${PG_BIN:-}/pg_ctl" ]] || { echo 'Install PostgreSQL 17 (macOS: brew install postgresql@17), or set PG_BIN'; exit 1; }
"$PG_BIN/postgres" --version | grep -Eq ' 17\.' || { echo 'PostgreSQL 17 is required'; exit 1; }
PG_DATA="$ROOT/data/postgres-native"
mkdir -p data/run data/logs
case "${1:-status}" in
 start)
  if [[ -f data/postgres/PG_VERSION && ! -f data/run/native-db-migrated ]]; then
   echo 'Legacy database exists. Complete and verify its logical migration before starting the native database.'; exit 1
  fi
  if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
   pwfile=$(mktemp "$ROOT/data/run/pg-password.XXXXXX")
   trap 'rm -f "$pwfile"' EXIT
   printf '%s\n' "${DB_PASSWORD:-local-development-only}" > "$pwfile"
   "$PG_BIN/initdb" -D "$PG_DATA" -U "${DB_USER:-insightradar}" --encoding=UTF8 --locale=C --auth-local=scram-sha-256 --auth-host=scram-sha-256 --pwfile="$pwfile" > data/logs/postgres-init.log
   rm -f "$pwfile"; trap - EXIT
  fi
  [[ "$(cat "$PG_DATA/PG_VERSION")" == 17 ]] || { echo 'Existing cluster has a different major version'; exit 1; }
  if ! "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; then
   "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$ROOT/data/logs/postgres.log" -o "-h 127.0.0.1 -p 15432 -k '$ROOT/data/run'" -w -t 30 start
  fi
  export PGPASSWORD="${DB_PASSWORD:-local-development-only}"
  exists=$("$PG_BIN/psql" -X -h 127.0.0.1 -p 15432 -U "${DB_USER:-insightradar}" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='insightradar_v002'")
  if [[ "$exists" != 1 ]]; then "$PG_BIN/createdb" -h 127.0.0.1 -p 15432 -U "${DB_USER:-insightradar}" insightradar_v002; fi
  ;;
 stop)
  if [[ -f "$PG_DATA/PG_VERSION" ]] && "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; then
   "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast -w -t 30 stop
  fi
  ;;
 status) "$PG_BIN/pg_ctl" -D "$PG_DATA" status ;;
 *) echo 'Usage: scripts/postgres.sh start|stop|status'; exit 2 ;;
esac
