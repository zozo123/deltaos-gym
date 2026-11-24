#!/usr/bin/env python3
"""Release QA: what must be true before a release, measured and written to one report.

  release_qa.py [--seeds N] [--jobs J] [--kernel] [--tasks a,b] [--out FILE] [--allow-same-uid]

1. Static package checks and the vendored-harness check.
2. Unit tests (harness, gym runtime, instrumentation).
3. For every task, N graded episodes (fresh seed each) of the reference, the starter and
   every control. References and positive controls (p*) must be accepted every time;
   the starter and negative controls (m*, x*) must be rejected every time.
4. Every receipt must validate against contracts/receipt.schema.json.

Run it as root in a container: exploits are only asserted under uid separation.
--kernel additionally requires the kernel tier (privileged container, disposable VM).
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from grade_local import ROOT, grade  # noqa: E402
from validate_receipt import validate  # noqa: E402

UNIT_SUITES = ["harness/tests", "gym_runtime/tests", "instrumentation/tests"]


def step(title, argv):
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=900,
                          env={**os.environ, "PYTHONPATH": str(ROOT)})
    print(f"[{'ok' if proc.returncode == 0 else 'FAIL'}] {title}", flush=True)
    return proc


def unit_tests():
    results = []
    for suite in UNIT_SUITES:
        if not (ROOT / suite).is_dir():
            continue
        proc = step(f"unit tests {suite}", [sys.executable, "-m", "unittest", "discover", "-s", suite])
        ran = re.search(r"Ran (\d+) tests?", proc.stderr)
        skipped = re.search(r"skipped=(\d+)", proc.stderr)
        results.append({"suite": suite, "ran": int(ran.group(1)) if ran else 0,
                        "skipped": int(skipped.group(1)) if skipped else 0,
                        "ok": proc.returncode == 0, "tail": "" if proc.returncode == 0 else proc.stderr[-1500:]})
    return results


def plan_for(task: str):
    plan = [("oracle", "oracle", 1, "reference"), ("starter", "starter", 0, "starter")]
    controls = ROOT / "qa" / "controls" / task
    for path in sorted(controls.iterdir()) if controls.is_dir() else []:
        kind = {"m": "honest mistake", "x": "exploit", "p": "correct alternative"}.get(path.name[0])
        if kind:
            plan.append((path.name, str(path), 1 if path.name[0] == "p" else 0, kind))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--kernel", action="store_true")
    parser.add_argument("--tasks")
    parser.add_argument("--out", default=str(ROOT / "qa" / "reports" / "release-report.json"))
    parser.add_argument("--allow-same-uid", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0 and sys.platform.startswith("linux")
    if not is_root and not args.allow_same_uid:
        print("release QA asserts exploit controls and therefore needs root on Linux (a container is fine).\n"
              "Use --allow-same-uid for a weaker local run.")
        return 2

    static = [step("package checks", [sys.executable, "scripts/check_package.py"]),
              step("vendored harness", [sys.executable, "scripts/vendor_harness.py", "--check"])]
    units = unit_tests()

    tasks = sorted(p.name for p in (ROOT / "tasks").iterdir() if p.is_dir())
    if args.tasks:
        tasks = [t for t in tasks if t in args.tasks.split(",")]
    jobs = [(task, label, candidate, want, kind, run)
            for task in tasks for (label, candidate, want, kind) in plan_for(task) for run in range(args.seeds)]
    slots = list(range(args.jobs))
    lock = threading.Lock()

    def one(job):
        task, label, candidate, want, kind, run = job
        with lock:
            slot = slots.pop()
        try:
            env = {"DELTAOS_SANDBOX_UID": str(60000 + 10 * slot), "DELTAOS_SANDBOX_GID": str(60000 + 10 * slot),
                   "DELTAOS_OBSERVER_UID": str(60005 + 10 * slot)}
            receipt = grade(task, candidate, kernel=args.kernel, extra_env=env)
        finally:
            with lock:
                slots.append(slot)
        got = 1 if receipt.get("_reward_file") == "1" else 0
        clean = {k: v for k, v in receipt.items() if not k.startswith("_")}
        invalid = validate(clean) if "schema" in clean else ["no receipt written"]
        return {"task": task, "candidate": label, "kind": kind, "run": run, "expected": want, "reward": got,
                "ok": got == want and receipt.get("reward") == got and not invalid,
                "assurance": receipt.get("assurance"),
                "reason": (receipt.get("counterexample") or {}).get("reason") or receipt.get("error"),
                "failed_checks": sorted(k for k, v in (receipt.get("checks") or {}).items() if v is False),
                "checks": receipt.get("checks"), "evidence": receipt.get("evidence"),
                "seed": receipt.get("seed"), "seconds": receipt.get("_seconds"),
                "isolation": (receipt.get("isolation") or {}).get("mode"),
                "kernel_profile": receipt.get("kernel_profile"), "receipt_problems": invalid}

    rows = []
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for row in pool.map(one, jobs):
            rows.append(row)
            if not row["ok"]:
                print(f"FAIL {row['task']} {row['candidate']} reward={row['reward']} want={row['expected']} "
                      f"{row['assurance']} {row['reason']} {row['receipt_problems']}", flush=True)

    per_task = {}
    for task in tasks:
        mine = [r for r in rows if r["task"] == task]
        good = [r for r in mine if r["expected"] == 1]
        bad = [r for r in mine if r["expected"] == 0]
        oracle = next(r for r in mine if r["candidate"] == "oracle")
        candidates = {}
        for r in mine:
            entry = candidates.setdefault(r["candidate"], {"kind": r["kind"], "expected": r["expected"],
                                                             "rewards": [], "reasons": [], "assurance": []})
            entry["rewards"].append(r["reward"])
            for key, value in (("reasons", r["reason"]), ("assurance", r["assurance"])):
                if value and value not in entry[key]:
                    entry[key].append(value)
        per_task[task] = {
            "episodes": len(mine),
            "correct_accepted": sum(r["reward"] for r in good), "correct_total": len(good),
            "wrong_rejected": sum(1 - r["reward"] for r in bad), "wrong_total": len(bad),
            "reference_assurance": oracle["assurance"],
            "reference_evidence": [{k: e[k] for k in ("class", "claim", "status", "scope")}
                                   for e in (oracle["evidence"] or [])],
            "reference_checks": oracle["checks"],
            "seconds_mean": round(sum(r["seconds"] or 0 for r in mine) / len(mine), 2),
            "seconds_max": max(r["seconds"] or 0 for r in mine),
            "isolation": sorted({r["isolation"] for r in mine if r["isolation"]}),
            "candidates": candidates,
        }
        t = per_task[task]
        print(f"{task:30s} correct accepted {t['correct_accepted']}/{t['correct_total']}  wrong rejected "
              f"{t['wrong_rejected']}/{t['wrong_total']}  reference: {t['reference_assurance']}  "
              f"mean {t['seconds_mean']}s", flush=True)

    ok = (all(s.returncode == 0 for s in static) and all(u["ok"] for u in units) and all(r["ok"] for r in rows)
          and (is_root or args.allow_same_uid))
    from deltaos_harness_info import facts  # noqa: E402
    report = {
        "release": facts()["version"],
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": ok,
        "scope": "graders run on shipped references, starters and controls; no model-written code involved",
        "environment": {**facts(), "kernel_release": platform.release(), "machine": platform.machine(),
                        "python": platform.python_version(), "root": is_root,
                        "kernel_tier": "required" if args.kernel else "off"},
        "seeds_per_candidate": args.seeds,
        "static_checks_ok": all(s.returncode == 0 for s in static),
        "unit_tests": units,
        "totals": {
            "tasks": len(tasks), "episodes": len(rows),
            "correct_accepted": sum(t["correct_accepted"] for t in per_task.values()),
            "correct_total": sum(t["correct_total"] for t in per_task.values()),
            "wrong_rejected": sum(t["wrong_rejected"] for t in per_task.values()),
            "wrong_total": sum(t["wrong_total"] for t in per_task.values()),
            "negative_controls": sum(1 for t in tasks for p in plan_for(t) if p[3] in ("honest mistake", "exploit")),
            "positive_controls": sum(1 for t in tasks for p in plan_for(t) if p[3] == "correct alternative"),
            "receipts_valid": sum(1 for r in rows if not r["receipt_problems"]),
        },
        "tasks": per_task,
        "duration_sec": round(time.monotonic() - started, 1),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")
    print("SUMMARY", json.dumps({**report["totals"], "passed": ok, "duration_sec": report["duration_sec"]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
