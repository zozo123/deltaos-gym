#!/bin/sh
# Run every negative control against the ORIGINAL v0.5 graders the way a Harbor
# verifier container would (/workspace, /tests, /logs/verifier), one fresh container each.
# Output: TSV  task <tab> control <tab> exit <tab> reward
# Usage: V05=/path/to/DeltaOS-Research-Gym-v0.5 [IMAGE=deltaos-dev] sh scripts/legacy_escape_matrix.sh
# IMAGE needs gcc, clang, libbpf-dev and python3 (see qa/Dockerfile.dev).
V05=${V05:?set V05 to an unpacked DeltaOS-Research-Gym-v0.5 directory}
CTL=$(cd "$(dirname "$0")/.." && pwd)/qa/controls
IMAGE=${IMAGE:-deltaos-dev}
art() { case "$1" in egress-policy-delta) echo policy.c;; quota-overflow-preservation) echo quota.c;;
        vfs-crash-atomicity) echo publisher.c;; probe-design) echo solver.py;; fd-capability-boundary) echo spawn.c;; esac; }
run() { # task label mode(file|oracle|starter) [file]
  docker run --rm -v $V05:/v05:ro -v $CTL:/controls:ro $IMAGE bash -c '
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
  for f in $(ls $CTL/$task); do run $task $f file; done
done
