#!/bin/sh
# Grade every candidate in qa/controls/ with the ORIGINAL v0.5 graders (legacy/v0.5),
# the way a Harbor verifier container would lay things out (/workspace, /tests,
# /logs/verifier), one fresh container per candidate.
#
# Usage: [V05=legacy/v0.5] [IMAGE=deltaos-dev] sh scripts/legacy_escape_matrix.sh > v05.tsv
# IMAGE needs gcc, clang, libbpf-dev and python3 (qa/Dockerfile.dev has them).
# Output: TSV  task <tab> candidate <tab> exit status <tab> reward
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
V05=$(cd "${V05:-$ROOT/legacy/v0.5}" && pwd)
CTL=$ROOT/qa/controls
IMAGE=${IMAGE:-deltaos-dev}
art() { case "$1" in egress-policy-delta) echo policy.c;; quota-overflow-preservation) echo quota.c;;
        vfs-crash-atomicity) echo publisher.c;; probe-design) echo solver.py;; fd-capability-boundary) echo spawn.c;; esac; }
run() { # task label mode(file|oracle|starter)
  docker run --rm -v "$V05":/v05:ro -v "$CTL":/controls:ro "$IMAGE" bash -c '
    task=$1; label=$2; mode=$3; art=$4
    mkdir -p /workspace /logs/verifier /tests /solution
    cp -r /v05/tasks/$task/tests/. /tests/
    for f in /v05/tasks/$task/environment/*; do case "$f" in *Dockerfile) ;; *) cp "$f" /workspace/;; esac; done
    cp -r /v05/tasks/$task/solution/. /solution/
    case "$mode" in
      file) cp "/controls/$task/$label" "/workspace/$art";;
      oracle) sh /solution/solve.sh;;
      starter) : ;;
    esac
    rm -rf /solution
    timeout 150 sh /tests/test.sh >/tmp/out.log 2>&1; rc=$?
    sleep 0.6
    printf "%s\t%s\t%s\t%s\n" "$task" "$label" "$rc" "$(tr -d "\n" < /logs/verifier/reward.txt 2>/dev/null || echo MISSING)"
  ' _ "$1" "$2" "$3" "$(art "$1")"
}
for task in egress-policy-delta quota-overflow-preservation vfs-crash-atomicity probe-design fd-capability-boundary; do
  run $task ORACLE oracle
  run $task STARTER starter
  for f in $(ls "$CTL/$task"); do run $task "$f" file; done
done
