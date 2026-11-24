"""Baseline policies for the diagnosis environment."""
from __future__ import annotations

import random

from .scenarios import consistent_hypotheses, informative_probes


class GuessPolicy:
    """Answers a random hypothesis without looking."""
    name = "guess"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def act(self, observation: dict) -> dict:
        return {"type": "answer", "hypothesis": self.rng.choice(observation["hypotheses"])}


class OneProbePolicy:
    """Observes the cheapest probe once, then answers the first hypothesis that still fits."""
    name = "one-probe"

    def act(self, observation: dict) -> dict:
        case = observation
        if not observation["history"]:
            affordable = [p for p in case["probes"] if p["cost"] <= observation["remaining_budget"]]
            if affordable:
                return {"type": "observe", "name": min(affordable, key=lambda p: (p["cost"], p["name"]))["name"]}
        fits = consistent_hypotheses(case, observation["history"])
        return {"type": "answer", "hypothesis": fits[0] if fits else case["hypotheses"][0]}


class CarefulPolicy:
    """Probes until one hypothesis fits; abstains when nothing affordable can separate the rest."""
    name = "careful"

    def act(self, observation: dict) -> dict:
        case = observation
        fits = consistent_hypotheses(case, observation["history"])
        if len(fits) == 1:
            return {"type": "answer", "hypothesis": fits[0]}
        useful = informative_probes(case, fits, observation["remaining_budget"])
        if not useful:
            return {"type": "abstain"}
        probes = {p["name"]: p for p in case["probes"]}

        def score(name):
            readings = probes[name]["readings"]
            distinct = len({frozenset(map(repr, readings[h])) for h in fits})
            return (-distinct, probes[name]["cost"], name)
        return {"type": "observe", "name": min(useful, key=score)}


POLICIES = [GuessPolicy, OneProbePolicy, CarefulPolicy]
