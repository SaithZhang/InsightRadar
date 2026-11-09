#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ "$(uname)" == Darwin ]]; then export JAVA_HOME="$(/usr/libexec/java_home -v 21)"; fi
export PATH="${JAVA_HOME:+$JAVA_HOME/bin:}$PATH"
mkdir -p data/run data/logs
for service in server web; do
 if [[ -f "data/run/$service.pid" ]] && kill -0 "$(cat "data/run/$service.pid")" 2>/dev/null; then
  echo "$service already running; stop this project before restarting"; exit 1
 fi
done
[[ -x .venv/bin/python ]] || { echo 'Run python3 -m venv .venv and install bridge/requirements.txt first'; exit 1; }
scripts/postgres.sh start
mvn -q -f server/pom.xml package -DskipTests
npm run build --prefix web
(
 if [[ -n "${LLM_KEY_ENV_FILE:-}" && -z "${LLM_API_KEY:-}" ]]; then
  source "$LLM_KEY_ENV_FILE"
  export LLM_API_KEY="${OPENAI_API_KEY:?Configured key file must define OPENAI_API_KEY}"
  unset OPENAI_API_KEY
 fi
 .venv/bin/python scripts/launch_process.py server
)
for ((i=0;i<40;i++)); do
 if curl -fsS http://127.0.0.1:18080/api/v1/health > /dev/null 2>&1; then break; fi
 sleep 1
done
curl -fsS http://127.0.0.1:18080/api/v1/health > /dev/null
.venv/bin/python scripts/launch_process.py web
for ((i=0;i<20;i++)); do
 if curl -fsS http://127.0.0.1:15173 > /dev/null 2>&1; then break; fi
 sleep 1
done
printf '%s\n' 'Open http://127.0.0.1:15173 · logs in data/logs · stop: scripts/stop.sh'
