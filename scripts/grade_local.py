#!/usr/bin/env python3
"""Grade one candidate the way a verifier container would, in throwaway directories.

  grade_local.py TASK oracle
  grade_local.py TASK starter
  grade_local.py TASK path/to/candidate            (copied over the task's artifact)
  options: --seed HEX   replay an episode      --kernel   DELTAOS_KERNEL_TIER=required
           --degraded   allow missing tools    --print    print the whole receipt

Run it as root inside a container to get uid-separated isolation; as a normal user
it still works, with isolation reported as "same-uid" (trusted fixtures only).
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def task_artifacts(task: str) -> list[str]:
    config = tomllib.loads((ROOT / "tasks" / task / "task.toml").read_text())
    return [pathlib.PurePosixPath(a).name for a in config["artifacts"]]


def grade(task: str, candidate: str, *, seed: str | None = None, kernel: bool = False,
          degraded: bool = False, timeout: float = 900.0, extra_env: dict | None = None) -> dict:
    """Returns the receipt, plus "_reward_file" (what Harbor would read) and "_seconds"."""
    task_dir = ROOT / "tasks" / task
    artifacts = task_artifacts(task)
    with tempfile.TemporaryDirectory(prefix="deltaos-grade-") as tmp:
        tmp = pathlib.Path(tmp)
        os.chmod(tmp, 0o755)
        workspace, tests, logs = tmp / "workspace", tmp / "tests", tmp / "logs"
        workspace.mkdir()
        logs.mkdir()
        shutil.copytree(task_dir / "tests", tests)
        for item in sorted((task_dir / "environment").iterdir()):
            if item.is_file() and item.name not in ("Dockerfile", "docker-compose.yaml"):
                shutil.copy(item, workspace / item.name)
        if candidate == "oracle":
            for name in artifacts:
                shutil.copy(task_dir / "solution" / name, workspace / name)
        elif candidate != "starter":
            if len(artifacts) != 1:
                raise SystemExit("a candidate file needs a single-artifact task")
            shutil.copy(candidate, workspace / artifacts[0])
        env = {k: v for k, v in os.environ.items() if not k.startswith("DELTAOS_")}
        env.update(DELTAOS_WORKSPACE=str(workspace), DELTAOS_TESTS=str(tests), DELTAOS_LOGS=str(logs))
        if seed:
            env["DELTAOS_SEED"] = seed
        if kernel:
            env["DELTAOS_KERNEL_TIER"] = "required"
        if degraded:
            env["DELTAOS_ALLOW_DEGRADED"] = "1"
        env.update(extra_env or {})
        import time
        started = time.monotonic()
        proc = subprocess.run(["sh", str(tests / "test.sh")], env=env, cwd=workspace,
                              capture_output=True, text=True, timeout=timeout)
        seconds = time.monotonic() - started
        time.sleep(0.3)        # anything a candidate left running has had its chance
        reward_file = (logs / "reward.txt").read_text().strip() if (logs / "reward.txt").is_file() else "MISSING"
        try:
            receipt = json.loads((logs / "receipt.json").read_text())
        except (OSError, ValueError):
            receipt = {"reward": 0, "assurance": "UNKNOWN", "error": "no receipt: " + proc.stderr[-500:]}
        receipt["_reward_file"] = reward_file
        receipt["_seconds"] = round(seconds, 2)
        receipt["_exit"] = proc.returncode
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task")
    parser.add_argument("candidate")
    parser.add_argument("--seed")
    parser.add_argument("--kernel", action="store_true")
    parser.add_argument("--degraded", action="store_true")
    parser.add_argument("--print", action="store_true", dest="show")
    args = parser.parse_args()
    receipt = grade(args.task, args.candidate, seed=args.seed, kernel=args.kernel, degraded=args.degraded)
    if args.show:
        print(json.dumps(receipt, indent=2))
    else:
        brief = {k: receipt.get(k) for k in ("task_id", "reward", "assurance", "checks", "seed",
                                             "counterexample", "error", "_reward_file", "_seconds")}
        brief["isolation"] = (receipt.get("isolation") or {}).get("mode")
        print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
