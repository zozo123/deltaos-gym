#!/usr/bin/env python3
"""Static checks on the task packages. No candidate code is executed.

For every task: the manifest has the fields Harbor reads, the files a Harbor trial
needs exist, the vendored harness is the canonical one, the reference solution and
solve.sh agree with the declared artifacts, and the negative and positive controls
that release QA relies on are present.
"""
import hashlib
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = ["instruction.md", "task.toml", "environment/Dockerfile", "solution/solve.sh",
            "tests/Dockerfile", "tests/test.sh", "tests/grade.py", "tests/deltaos_harness.py"]


def check_task(task: pathlib.Path, harness_digest: str) -> list[str]:
    problems = []
    for name in REQUIRED:
        if not (task / name).is_file():
            problems.append(f"missing {name}")
    if problems:
        return problems
    config = tomllib.loads((task / "task.toml").read_text())
    if config.get("schema_version") != "1.4":
        problems.append("schema_version must be 1.4")
    package = config.get("task", {})
    if package.get("name") != f"deltaos/{task.name}":
        problems.append("[task].name must be deltaos/<directory name>")
    if not package.get("version"):
        problems.append("[task].version missing")
    verifier = config.get("verifier", {})
    if verifier.get("environment_mode") != "separate":
        problems.append("[verifier].environment_mode must be separate")
    for section in (config.get("environment", {}), verifier.get("environment", {})):
        if section.get("network_mode") != "no-network":
            problems.append("network_mode must be no-network for the agent and the verifier")
    artifacts = config.get("artifacts") or []
    if not artifacts or not all(a.startswith("/workspace/") for a in artifacts):
        problems.append("artifacts must be files under /workspace/")
    solve = (task / "solution" / "solve.sh").read_text()
    for artifact in artifacts:
        name = pathlib.PurePosixPath(artifact).name
        if not (task / "solution" / name).is_file():
            problems.append(f"solution/{name} missing")
        if f"cp /solution/{name} /workspace/{name}" not in solve:
            problems.append(f"solve.sh must copy /solution/{name} to /workspace/{name}")
        if not (task / "environment" / name).is_file():
            problems.append(f"environment/{name} (the starter) missing")
        if name not in (task / "instruction.md").read_text():
            problems.append(f"instruction.md never names {name}")
    if hashlib.sha256((task / "tests" / "deltaos_harness.py").read_bytes()).hexdigest() != harness_digest:
        problems.append("tests/deltaos_harness.py differs from harness/deltaos_harness.py (run scripts/vendor_harness.py)")
    for shared in sorted(p.name for p in (task / "environment").iterdir() if p.suffix == ".h"):
        twin = task / "tests" / shared
        if twin.is_file() and twin.read_bytes() != (task / "environment" / shared).read_bytes():
            problems.append(f"{shared} differs between environment/ and tests/")
    if "chmod -R go-rwx /tests /logs" not in (task / "tests" / "Dockerfile").read_text():
        problems.append("tests/Dockerfile must end by making /tests and /logs private")
    for forbidden in ("solution", "tests"):
        if f"COPY {forbidden}" in (task / "environment" / "Dockerfile").read_text():
            problems.append(f"environment/Dockerfile copies {forbidden}/ into the agent image")
    controls = ROOT / "qa" / "controls" / task.name
    kinds = {k: len(list(controls.glob(k + "[0-9]*"))) if controls.is_dir() else 0 for k in "mxp"}
    if kinds["m"] + kinds["x"] < 4:
        problems.append("fewer than 4 negative controls (qa/controls/<task>/m*, x*)")
    if kinds["p"] < 2:
        problems.append("fewer than 2 positive controls (qa/controls/<task>/p*)")
    return problems


def main() -> int:
    harness_digest = hashlib.sha256((ROOT / "harness" / "deltaos_harness.py").read_bytes()).hexdigest()
    failed = False
    tasks = sorted(p for p in (ROOT / "tasks").iterdir() if p.is_dir())
    for task in tasks:
        problems = check_task(task, harness_digest)
        failed = failed or bool(problems)
        print(f"{task.name:32s} {'OK' if not problems else 'PROBLEMS'}")
        for problem in problems:
            print("    - " + problem)
    print(f"{len(tasks)} tasks checked.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
