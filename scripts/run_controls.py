#!/usr/bin/env python3
"""Run a task's reference, starter and every negative/positive control through its grader.

  run_controls.py TASK [--seeds N] [--kernel] [--json OUT]

Expectations: oracle and qa/controls/TASK/p* must get reward 1; the starter and
qa/controls/TASK/{m*,x*} must get reward 0. The reward that counts is the one in
reward.txt after the grader and anything it started have gone away.
Exit status 1 if any expectation is broken.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from grade_local import ROOT, grade  # noqa: E402


def run(task: str, seeds: int, kernel: bool) -> tuple[list[dict], bool]:
    controls = sorted((ROOT / "qa" / "controls" / task).iterdir()) if (ROOT / "qa" / "controls" / task).is_dir() else []
    plan = [("oracle", "oracle", 1), ("starter", "starter", 0)]
    for path in controls:
        if path.name.startswith("."):
            continue
        plan.append((path.name, str(path), 1 if path.name.startswith("p") else 0))
    rows, ok = [], True
    for label, candidate, want in plan:
        for index in range(seeds):
            receipt = grade(task, candidate, kernel=kernel)
            got = 1 if receipt.get("_reward_file") == "1" else 0
            good = got == want and receipt.get("reward") == got
            ok = ok and good
            reason = (receipt.get("counterexample") or {}).get("reason") or receipt.get("error")
            rows.append({"task": task, "candidate": label, "run": index, "expected": want, "reward": got,
                         "ok": good, "assurance": receipt.get("assurance"), "reason": reason,
                         "seed": receipt.get("seed"), "seconds": receipt.get("_seconds"),
                         "isolation": (receipt.get("isolation") or {}).get("mode"),
                         "checks": receipt.get("checks")})
            print(f"{'ok  ' if good else 'FAIL'} {task:28s} {label:42s} reward={got} want={want} "
                  f"{receipt.get('assurance'):20s} {str(reason or '')[:60]}", flush=True)
    return rows, ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--kernel", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args()
    rows, ok = run(args.task, args.seeds, args.kernel)
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(rows, indent=1) + "\n")
    print("ALL EXPECTATIONS MET" if ok else "EXPECTATIONS BROKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
