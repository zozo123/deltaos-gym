#!/bin/bash
# Harbor end to end: `harbor lint`, then the reference agent (oracle) and the do-nothing
# agent (nop) on every task. Needs Linux, Docker and Harbor (`uv tool install harbor`).
#
# Usage: scripts/harbor_e2e.sh [OUT_DIR] [--public-network]
# --public-network runs copies of the tasks with network_mode = "public", for hosts
# whose kernel lacks CONFIG_NFT_FIB_INET (Harbor then cannot enforce "no-network").
# Summarise with: python3 scripts/harbor_summary.py OUT_DIR > qa/reports/harbor-e2e.json
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-/tmp/deltaos-harbor}
PUBLIC=${2:-}
rm -rf "$OUT"; mkdir -p "$OUT/tasks" "$OUT/jobs"
cd "$ROOT"
harbor lint tasks/* > "$OUT/lint.txt" 2>&1; echo "LINT_EXIT=$?" >> "$OUT/lint.txt"
for t in $(ls tasks); do
  cp -r "tasks/$t" "$OUT/tasks/$t"
  if [ "$PUBLIC" = "--public-network" ]; then
    sed -i 's/network_mode = "no-network"/network_mode = "public"/' "$OUT/tasks/$t/task.toml"
  fi
  for agent in oracle nop; do
    harbor run -p "$OUT/tasks/$t" -a $agent --jobs-dir "$OUT/jobs/$t-$agent" > "$OUT/$t-$agent.log" 2>&1
    echo "$t $agent exit=$?" | tee -a "$OUT/progress.txt"
  done
done
echo DONE >> "$OUT/progress.txt"
