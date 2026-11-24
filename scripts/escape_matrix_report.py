#!/usr/bin/env python3
"""Turn the TSV from scripts/legacy_escape_matrix.sh into qa/reports/v05-escape-matrix.json.

  escape_matrix_report.py v05.tsv > qa/reports/v05-escape-matrix.json

The summary keeps two sets apart. "Before the rewrite" is what the write-up's headline
is about: the 20 mutants v0.5 shipped with and the 27 candidates written against v0.5
before any grader changed. "Added later" are controls written while building 1.0, kept
here so a rerun matches the report line for line.
"""
import json
import pathlib
import platform
import sys

FIRST_27 = {
    "egress-policy-delta": ["m05-proto-truncation.c", "m06-uid-truncation.c", "m07-ip-high-byte-mask.c",
                            "x01-ifdef-bpf-allow-all.c", "x02-atexit-reward-overwrite.c", "x03-magic-backdoor.c",
                            "x04-time-bomb.c"],
    "quota-overflow-preservation": ["x01-ifdef-bpf-free-quota.c", "x02-exit-after-forged-reward.c",
                                    "x03-magic-amount-backdoor.c", "x04-time-bomb.c"],
    "vfs-crash-atomicity": ["m05-fsync-after-close.c", "m06-fsync-retry-after-eio.c",
                            "m07-eintr-restart-from-zero.c", "m08-eintr-retried-once.c", "m09-dir-fsync-retry.c",
                            "m10-remove-recreate-empty.c", "x01-stdout-forge.c"],
    "probe-design": ["x01-import-oracle.py", "x02-reward-daemon.py"],
    "fd-capability-boundary": ["m05-ignore-authorized-fd.c", "m06-ignore-exit-status.c", "m07-no-eintr-retry.c",
                               "m08-parent-dup2-clobber.c", "m09-leak-high-fd.c", "x01-forge-receipt.c",
                               "x02-stdout-forge.c"],
}


def kind(name):
    if name in ("ORACLE", "STARTER"):
        return name.lower() == "oracle" and "reference" or "starter"
    if name[:3] in ("m01", "m02", "m03", "m04"):
        return "shipped mutant"
    return {"m": "honest mistake", "x": "exploit", "p": "correct alternative"}[name[0]]


def main() -> int:
    rows = []
    for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        task, name, _, reward = parts
        group = ("before the rewrite" if kind(name) in ("reference", "starter", "shipped mutant")
                 or name in FIRST_27.get(task, []) else "added later")
        rows.append({"task": task, "candidate": name, "kind": kind(name), "set": group,
                     "v0.5_reward": int(reward) if reward in ("0", "1") else None})
    first = [r for r in rows if r["set"] == "before the rewrite" and r["kind"] in ("honest mistake", "exploit")]
    later_wrong = [r for r in rows if r["set"] == "added later" and r["kind"] in ("honest mistake", "exploit")]
    later_right = [r for r in rows if r["kind"] == "correct alternative"]
    summary = {
        "shipped_mutants_rejected": sum(1 for r in rows if r["kind"] == "shipped mutant" and r["v0.5_reward"] == 0),
        "shipped_mutants_total": sum(1 for r in rows if r["kind"] == "shipped mutant"),
        "new_wrong_candidates_accepted": sum(r["v0.5_reward"] == 1 for r in first),
        "new_wrong_candidates_total": len(first),
        "honest_mistakes_accepted": sum(r["v0.5_reward"] == 1 for r in first if r["kind"] == "honest mistake"),
        "honest_mistakes_total": sum(1 for r in first if r["kind"] == "honest mistake"),
        "exploits_accepted": sum(r["v0.5_reward"] == 1 for r in first if r["kind"] == "exploit"),
        "exploits_total": sum(1 for r in first if r["kind"] == "exploit"),
        "later_wrong_candidates_accepted": sum(r["v0.5_reward"] == 1 for r in later_wrong),
        "later_wrong_candidates_total": len(later_wrong),
        "correct_alternatives_accepted": sum(r["v0.5_reward"] == 1 for r in later_right),
        "correct_alternatives_total": len(later_right),
    }
    print(json.dumps({
        "what": ("Every candidate in qa/controls/ for the five v0.5 tasks, graded by the original v0.5 graders "
                 "(legacy/v0.5), each in a fresh container laid out like a Harbor verifier. The reward is the "
                 "content of reward.txt 0.6 s after test.sh returned."),
        "how": "scripts/legacy_escape_matrix.sh, then scripts/escape_matrix_report.py",
        "host": f"Linux {platform.release()} {platform.machine()}",
        "summary": summary,
        "rows": rows,
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
