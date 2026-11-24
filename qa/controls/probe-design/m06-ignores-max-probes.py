"""Honest-mistake class: respects the budget but not max_probes."""
from itertools import combinations


def select_probes(case):
    hs = case["hypotheses"]
    probes = sorted(case["probes"], key=lambda p: p["name"])
    pairs = [(a, b) for i, a in enumerate(hs) for b in hs[i + 1:]]
    best = None
    for k in range(0, len(probes) + 1):
        for chosen in combinations(probes, k):
            cost = sum(p["cost"] for p in chosen)
            if cost > case["budget"]:
                continue
            if all(any(set(p["readings"][a]).isdisjoint(p["readings"][b]) for p in chosen) for a, b in pairs):
                key = (cost, k, [p["name"] for p in chosen])
                if best is None or key < best:
                    best = key
    if best is None:
        return {"selected": None}
    return {"selected": best[2], "cost": best[0]}
