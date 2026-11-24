#!/usr/bin/env python3
"""Validate receipts against contracts/receipt.schema.json with the standard library only.

  validate_receipt.py RECEIPT.json [...]

Supports the JSON Schema keywords the receipt schema uses: type, required, properties,
items, enum, const, pattern, minimum, maximum, minLength. Also enforces the two rules a
schema cannot say: a passed receipt has no failed check or evidence, and a receipt with
assurance X carries passing evidence of class X.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts" / "receipt.schema.json").read_text())
TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool,
         "number": (int, float), "null": type(None)}


def _is(value, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPES[name])


def problems(value, schema, where="receipt") -> list[str]:
    found = []
    if "const" in schema and value != schema["const"]:
        found.append(f"{where}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, name) for name in names):
            return found + [f"{where}: expected {' or '.join(names)}"]
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            found.append(f"{where}: does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            found.append(f"{where}: too short")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{where}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{where}: above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{where}: missing {key}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                found += problems(value[key], sub, f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            found += problems(item, schema["items"], f"{where}[{index}]")
    return found


def validate(receipt) -> list[str]:
    found = problems(receipt, SCHEMA)
    if found:
        return found
    if receipt["passed"] != (receipt["reward"] == 1):
        found.append("receipt: passed and reward disagree")
    if receipt["passed"]:
        if any(v is False for v in receipt["checks"].values()):
            found.append("receipt: passed with a failed check")
        if any(e["status"] == "fail" for e in receipt["evidence"]):
            found.append("receipt: passed with failed evidence")
        if not any(e["class"] == receipt["assurance"] and e["status"] == "pass" for e in receipt["evidence"]):
            found.append("receipt: assurance is not backed by passing evidence of that class")
        if receipt["counterexample"] is not None or receipt["error"] is not None:
            found.append("receipt: passed with a counterexample or an error")
    else:
        if receipt["assurance"] not in ("REFUTED", "UNKNOWN"):
            found.append("receipt: a failed run must be REFUTED or UNKNOWN")
        if receipt["assurance"] == "REFUTED" and receipt["counterexample"] is None:
            found.append("receipt: REFUTED without a counterexample")
    return found


def main() -> int:
    bad = 0
    for name in sys.argv[1:]:
        found = validate(json.loads(pathlib.Path(name).read_text()))
        bad += bool(found)
        print(name, "OK" if not found else "INVALID")
        for item in found:
            print("   -", item)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
