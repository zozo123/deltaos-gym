#!/usr/bin/env python3
"""Refuse to go on unless a receipt really covers the file in front of you.

  receipt_gate.py RECEIPT.json ARTIFACT [ARTIFACT ...] [--require CLASS ...] [--allow-same-uid]

Exit 0 only if the receipt is schema-valid, has reward 1, is not a degraded run, was
produced under uid separation, lists exactly the given files with matching SHA-256
digests, and carries passing evidence of every required class.

Meant as the step before a signature, for example:

  python3 scripts/receipt_gate.py receipt.json rpl_predicate.c \
      --require PROVED_WITHIN_MODEL --require KERNEL_ACCEPTED && shirudo build ...

A receipt is plain JSON. This gate checks that it matches the file; it cannot tell you
who wrote the receipt. Produce it yourself, or keep it somewhere you already trust.
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate_receipt import validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt")
    parser.add_argument("artifacts", nargs="+")
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--allow-same-uid", action="store_true")
    args = parser.parse_args()
    receipt = json.loads(pathlib.Path(args.receipt).read_text())
    refusals = validate(receipt)
    if not refusals:
        if receipt["reward"] != 1:
            refusals.append("the receipt records a failed run")
        if receipt["degraded"]:
            refusals.append("the receipt comes from a degraded run (a required tool was missing)")
        if receipt["isolation"]["mode"] != "uid-separated" and not args.allow_same_uid:
            refusals.append("the grader did not run under uid separation")
        recorded = {a["path"]: a["sha256"] for a in receipt["artifacts"]}
        given = {pathlib.Path(a).name: hashlib.sha256(pathlib.Path(a).read_bytes()).hexdigest()
                 for a in args.artifacts}
        if recorded != given:
            refusals.append("the receipt is for different bytes than the files given")
        held = {e["class"] for e in receipt["evidence"] if e["status"] == "pass"}
        for cls in args.require:
            if cls not in held:
                refusals.append(f"no passing {cls} evidence")
    for line in refusals:
        print("refused:", line)
    if not refusals:
        print(f"ok: {receipt['task_id']} {receipt['assurance']} {receipt['artifact_sha256'][:16]}")
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
