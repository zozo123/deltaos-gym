"""Diagnosis scenarios: validation and a seeded generator."""
from __future__ import annotations

import random
from typing import Any


class ScenarioError(ValueError):
    pass


def validate(case: Any) -> dict:
    """Raise ScenarioError with a clear message unless `case` is a well-formed scenario."""
    if not isinstance(case, dict):
        raise ScenarioError("a scenario is a JSON object")
    hyps = case.get("hypotheses")
    if not isinstance(hyps, list) or not hyps or not all(isinstance(h, str) and h for h in hyps):
        raise ScenarioError("'hypotheses' must be a non-empty list of names")
    if len(set(hyps)) != len(hyps):
        raise ScenarioError("hypothesis names must be unique")
    budget = case.get("budget")
    if type(budget) is not int or budget < 0:
        raise ScenarioError("'budget' must be a non-negative integer")
    probes = case.get("probes")
    if not isinstance(probes, list):
        raise ScenarioError("'probes' must be a list")
    names = set()
    for probe in probes:
        if not isinstance(probe, dict) or not isinstance(probe.get("name"), str) or not probe["name"]:
            raise ScenarioError("every probe needs a name")
        if probe["name"] in names:
            raise ScenarioError(f"probe {probe['name']!r} appears twice")
        names.add(probe["name"])
        if type(probe.get("cost")) is not int or probe["cost"] < 0:
            raise ScenarioError(f"probe {probe['name']!r}: 'cost' must be a non-negative integer")
        readings = probe.get("readings")
        if not isinstance(readings, dict) or set(readings) != set(hyps):
            raise ScenarioError(f"probe {probe['name']!r}: 'readings' must have exactly one entry per hypothesis")
        for h, values in readings.items():
            if not isinstance(values, list) or not values:
                raise ScenarioError(f"probe {probe['name']!r}: readings for {h!r} must be a non-empty list")
    return case


def consistent_hypotheses(case: dict, history: list[dict]) -> list[str]:
    """Hypotheses under which every observed value was possible, in scenario order."""
    probes = {p["name"]: p for p in case["probes"]}
    return [h for h in case["hypotheses"]
            if all(item["value"] in probes[item["probe"]]["readings"][h] for item in history)]


def informative_probes(case: dict, consistent: list[str], budget_left: int) -> list[str]:
    """Affordable probes whose possible readings differ between some consistent hypotheses."""
    found = []
    for probe in case["probes"]:
        if probe["cost"] > budget_left:
            continue
        sets = {frozenset(map(repr, probe["readings"][h])) for h in consistent}
        if len(sets) > 1:
            found.append(probe["name"])
    return found


def generate(seed: int, *, hypotheses: int = 4, probes: int = 5, budget: int | None = None,
             unobservable_pair: bool = False) -> dict:
    """A random scenario. With `unobservable_pair`, two hypotheses read identically on every probe."""
    rng = random.Random(seed)
    hyps = [f"cause-{i}" for i in range(hypotheses)]
    items = []
    for j in range(probes):
        readings = {}
        for h in hyps:
            v = rng.randrange(4)
            readings[h] = [v] if rng.random() < 0.6 else sorted({v, (v + 1) % 4})
        if unobservable_pair and hypotheses >= 2:
            readings[hyps[1]] = list(readings[hyps[0]])
        items.append({"name": f"probe-{j}", "cost": rng.randint(1, 4), "readings": readings})
    return validate({"hypotheses": hyps, "probes": items,
                     "budget": budget if budget is not None else rng.randint(4, 12)})
