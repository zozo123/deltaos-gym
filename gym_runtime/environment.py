"""Active, budgeted diagnosis with a hidden cause and lossy probes.

Runs in a trusted process: the hidden cause never leaves it. The scenario is an
explicit finite observation model, not a model of all of Linux.

Rewards (the episode's last step):
  answer, correct, and the observations rule out every other cause
                                             1 - 0.25 * cost_used / budget   justified_correct
  answer, correct, other causes still fit    0.0                              lucky_correct
  answer, wrong or unknown cause            -1.0                              wrong / invalid
  abstain, and no affordable probe can tell the remaining causes apart
                                            +0.5                              abstain_not_observable
  abstain otherwise                          0.0                              abstain_premature
  step limit reached                         0.0                              truncated
Penalties on non-final steps: unknown probe or action -0.05, probe over budget -0.1.
"""
from __future__ import annotations

import copy
import random
from typing import Any

from .scenarios import ScenarioError, consistent_hypotheses, informative_probes, validate


class DeltaOSEnvironment:
    def __init__(self, case: dict, hidden_cause: str | None = None, seed: int | None = None,
                 max_steps: int | None = None):
        self.case = copy.deepcopy(validate(case))
        if hidden_cause is not None and hidden_cause not in self.case["hypotheses"]:
            raise ScenarioError("unknown hidden cause")
        self.fixed_cause = hidden_cause
        self.max_steps = max_steps if max_steps is not None else 4 * len(self.case["probes"]) + 4
        self.rng = random.Random(seed)
        self.episode_id = None
        self.reset()

    # -- public view
    def _observation(self) -> dict:
        return copy.deepcopy({
            "hypotheses": self.case["hypotheses"],
            "probes": [{"name": p["name"], "cost": p["cost"], "readings": p["readings"]} for p in self.case["probes"]],
            "budget": self.case["budget"],
            "remaining_budget": self.remaining,
            "history": self.history,
        })

    def state(self) -> dict:
        return {"episode_id": self.episode_id, "step_count": self.steps, "done": self.done,
                "observation": self._observation()}

    # -- gym API
    def reset(self, seed: int | None = None, options: dict | None = None) -> tuple[dict, dict]:
        if seed is not None:
            self.rng = random.Random(seed)
        options = options or {}
        cause = options.get("hidden_cause") or self.fixed_cause
        if cause is None:
            cause = self.rng.choice(self.case["hypotheses"])
        if cause not in self.case["hypotheses"]:
            raise ScenarioError("unknown hidden cause")
        self.hidden = cause
        self.episode_id = options.get("episode_id", self.episode_id)
        self.remaining = self.case["budget"]
        self.history: list[dict] = []
        self.steps = 0
        self.done = False
        return self._observation(), {"status": "ready", "max_steps": self.max_steps,
                                     "assurance": "finite_stochastic_observation_model"}

    def _final(self, reward: float, outcome: str, **extra) -> tuple[dict, float, bool, bool, dict]:
        self.done = True
        consistent = consistent_hypotheses(self.case, self.history)
        info = {"outcome": outcome, "consistent_hypotheses": consistent,
                "cost_used": self.case["budget"] - self.remaining, **extra}
        return self._observation(), round(reward, 6), outcome != "truncated", outcome == "truncated", info

    def step(self, action: Any) -> tuple[dict, float, bool, bool, dict]:
        if self.done:
            raise RuntimeError("episode is over; call reset()")
        self.steps += 1
        kind = action.get("type") if isinstance(action, dict) else None
        if kind == "observe":
            probe = next((p for p in self.case["probes"] if p["name"] == action.get("name")), None)
            if probe is None:
                result = (self._observation(), -0.05, False, False, {"error": "unknown_probe"})
            elif probe["cost"] > self.remaining:
                result = (self._observation(), -0.1, False, False, {"error": "over_budget"})
            else:
                self.remaining -= probe["cost"]
                value = self.rng.choice(probe["readings"][self.hidden])
                self.history.append({"probe": probe["name"], "value": value, "cost": probe["cost"]})
                result = (self._observation(), 0.0, False, False,
                          {"measurement": {"probe": probe["name"], "value": value}})
        elif kind == "answer":
            guess = action.get("hypothesis")
            consistent = consistent_hypotheses(self.case, self.history)
            if guess not in self.case["hypotheses"]:
                return self._final(-1.0, "invalid")
            if guess != self.hidden:
                return self._final(-1.0, "wrong")
            if consistent == [guess]:
                used = self.case["budget"] - self.remaining
                return self._final(1.0 - 0.25 * used / max(1, self.case["budget"]), "justified_correct")
            return self._final(0.0, "lucky_correct")
        elif kind == "abstain":
            consistent = consistent_hypotheses(self.case, self.history)
            if len(consistent) > 1 and not informative_probes(self.case, consistent, self.remaining):
                return self._final(0.5, "abstain_not_observable")
            return self._final(0.0, "abstain_premature")
        else:
            result = (self._observation(), -0.05, False, False, {"error": "unknown_action"})
        if self.steps >= self.max_steps:
            return self._final(0.0, "truncated")
        return result
