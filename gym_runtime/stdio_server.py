"""JSONL bridge to the diagnosis environment, for a training harness in another process.

  python3 -m gym_runtime.stdio_server SCENARIO.json [--seed N] [--cause-file PATH] [--max-steps N]

One JSON object per line in, one per line out:
  {"op": "reset", "seed": 7, "episode_id": "e1"}
  {"op": "step", "action": {"type": "observe", "name": "proc-fd-inventory"}}
  {"op": "step", "action": {"type": "answer", "hypothesis": "fd-leak"}}
  {"op": "state"}
The hidden cause is drawn per episode, or read from --cause-file. It is never taken
from the command line, where other users could see it in the process list.
"""
from __future__ import annotations

import argparse
import json
import sys

from .environment import DeltaOSEnvironment
from .scenarios import ScenarioError


def handle(env: DeltaOSEnvironment, request) -> dict:
    if not isinstance(request, dict):
        return {"error": "each request is a JSON object"}
    op = request.get("op")
    if op == "reset":
        options = {"episode_id": request.get("episode_id")}
        seed = request.get("seed")
        if seed is not None and type(seed) is not int:
            return {"error": "seed must be an integer"}
        observation, info = env.reset(seed=seed, options=options)
        return {"observation": observation, "info": info, "reward": 0.0, "terminated": False, "truncated": False}
    if op == "step":
        if env.done:
            return {"error": "episode is over; send reset"}
        observation, reward, terminated, truncated, info = env.step(request.get("action"))
        return {"observation": observation, "reward": reward, "terminated": terminated, "truncated": truncated,
                "info": info}
    if op == "state":
        return env.state()
    return {"error": "unknown op; use reset, step or state"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m gym_runtime.stdio_server")
    parser.add_argument("scenario")
    parser.add_argument("legacy_cause", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--cause-file")
    parser.add_argument("--max-steps", type=int)
    args = parser.parse_args(argv)
    if args.legacy_cause is not None:
        parser.error("the hidden cause is not taken from the command line (it shows in ps); use --cause-file")
    cause = None
    if args.cause_file:
        with open(args.cause_file) as handle_:
            cause = handle_.read().strip()
    try:
        with open(args.scenario) as handle_:
            env = DeltaOSEnvironment(json.load(handle_), hidden_cause=cause, seed=args.seed,
                                     max_steps=args.max_steps)
    except (OSError, ValueError, ScenarioError) as exc:
        parser.error(str(exc))
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(env, json.loads(line))
        except ValueError:
            response = {"error": "not JSON"}
        except Exception as exc:                       # the bridge stays up
            response = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
