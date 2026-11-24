#!/usr/bin/env python3
"""Copy harness/deltaos_harness.py into every tasks/*/tests/ (a verifier image only gets tests/).

  vendor_harness.py           write the copies
  vendor_harness.py --check   exit 1 if any copy differs from the source
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "harness" / "deltaos_harness.py"


def main() -> int:
    check = "--check" in sys.argv
    wanted = SOURCE.read_bytes()
    stale = []
    for tests in sorted((ROOT / "tasks").glob("*/tests")):
        target = tests / SOURCE.name
        if target.is_file() and target.read_bytes() == wanted:
            continue
        stale.append(target.relative_to(ROOT).as_posix())
        if not check:
            target.write_bytes(wanted)
    if check and stale:
        print("stale harness copies:", ", ".join(stale))
        return 1
    print(("checked" if check else "vendored"), len(list((ROOT / "tasks").glob("*/tests"))), "copies;",
          len(stale), "stale" if check else "updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
