"""Mean reward of the baseline policies over seeded episodes.

  python3 -m gym_runtime.evaluate [--episodes N] [SCENARIO.json ...]
"""
from __future__ import annotations

import argparse
import json
import pathlib

from .environment import DeltaOSEnvironment
from .policies import POLICIES

ROOT = pathlib.Path(__file__).resolve().parents[1]


def evaluate(case: dict, episodes: int = 400) -> dict:
    results = {}
    for policy_class in POLICIES:
        env = DeltaOSEnvironment(case, seed=0)
        total, outcomes = 0.0, {}
        policy = policy_class() if policy_class.__name__ != "GuessPolicy" else policy_class(seed=1)
        for episode in range(episodes):
            observation, _ = env.reset(seed=episode)
            while True:
                observation, reward, terminated, truncated, info = env.step(policy.act(observation))
                if terminated or truncated:
                    total += reward
                    outcomes[info["outcome"]] = outcomes.get(info["outcome"], 0) + 1
                    break
        results[policy_class.name] = {"mean_reward": round(total / episodes, 3), "outcomes": outcomes}
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenarios", nargs="*")
    parser.add_argument("--episodes", type=int, default=400)
    args = parser.parse_args()
    paths = [pathlib.Path(p) for p in args.scenarios] or sorted((ROOT / "scenarios").glob("*.json"))
    for path in paths:
        print(path.name)
        for name, result in evaluate(json.loads(path.read_text()), args.episodes).items():
            print(f"  {name:10s} {result['mean_reward']:+.3f}  {result['outcomes']}")


if __name__ == "__main__":
    main()
