#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
for service in web server; do
 file="data/run/$service.pid"
 if [[ -f "$file" ]]; then
  while IFS= read -r pid; do
   command=$(ps -p "$pid" -o command= || true)
   if [[ "$service" == server && "$command" == *insightradar-0.2.0.jar* || "$service" == server && "$command" == *insightradar-v002-0.2.0.jar* ]] || [[ "$service" == web && "$command" == *vite.js*15173* ]]; then
    kill "$pid" 2>/dev/null || true
    for ((i=0;i<30;i++)); do
     if ! kill -0 "$pid" 2>/dev/null; then break; fi
     sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then echo "$service did not stop; database kept running"; exit 1; fi
   fi
  done < "$file"
  rm "$file"
 fi
done
scripts/postgres.sh stop
