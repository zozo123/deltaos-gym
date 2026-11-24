#!/usr/bin/env python3
"""Summarise the output of scripts/harbor_e2e.sh into one JSON report.

  harbor_summary.py OUT_DIR > qa/reports/harbor-e2e.json
"""
import glob, json, pathlib, re, shutil, subprocess, sys
BASE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/deltaos-harbor")
version = subprocess.run([shutil.which("harbor") or "harbor", "--version"], capture_output=True, text=True).stdout.strip()
lint = (BASE / "lint.txt").read_text()
tasks = []
for task in sorted(p.name for p in (BASE / "tasks").iterdir()):
    row = {"task": task}
    for agent in ("oracle", "nop"):
        results = glob.glob(str(BASE / "jobs" / f"{task}-{agent}" / "*" / "result.json"))
        mean = errors = None
        if results:
            data = json.loads(pathlib.Path(results[0]).read_text())
            for ev in (data.get("stats", {}).get("evals") or {}).values():
                mean = ev["metrics"][0]["mean"] if ev.get("metrics") else None
                errors = ev.get("n_errors")
        row[f"{agent}_reward"] = mean
        row[f"{agent}_errors"] = errors
        receipts = glob.glob(str(BASE / "jobs" / f"{task}-{agent}" / "*" / "*" / "verifier" / "receipt.json"))
        if receipts and agent == "oracle":
            receipt = json.loads(pathlib.Path(receipts[0]).read_text())
            row["oracle_assurance"] = receipt.get("assurance")
            row["oracle_isolation"] = receipt.get("isolation", {}).get("mode")
        if receipts and agent == "nop":
            receipt = json.loads(pathlib.Path(receipts[0]).read_text())
            row["nop_assurance"] = receipt.get("assurance")
    tasks.append(row)
print(json.dumps({
    "harbor_version": version,
    "lint_exit": int(re.search(r"LINT_EXIT=(\d+)", lint).group(1)),
    "lint_findings": lint.replace("LINT_EXIT=0", "").strip(),
    "note": ("Each trial ran with a separate verifier container built from tests/Dockerfile. This machine's kernel "
             "lacks CONFIG_NFT_FIB_INET, so Harbor's Docker backend cannot enforce network_mode = \"no-network\"; "
             "the trials ran on copies of the tasks with network_mode = \"public\"."),
    "tasks": tasks,
}, indent=1))
