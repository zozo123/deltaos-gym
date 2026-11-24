"""Correct alternative: dynamic programming over which hypothesis pairs are separated."""
from itertools import combinations


def select_probes(case):
    hyps = case["hypotheses"]
    pairs = list(combinations(hyps, 2))
    full = (1 << len(pairs)) - 1
    masks = []
    for p in case["probes"]:
        m = 0
        for bit, (a, b) in enumerate(pairs):
            if set(p["readings"][a]).isdisjoint(p["readings"][b]):
                m |= 1 << bit
        masks.append((p["name"], p["cost"], m))
    # state: (covered mask, number of probes) -> best (cost, sorted names)
    best = {(0, 0): (0, [])}
    for name, cost, m in sorted(masks):
        for (covered, count), (c, names) in list(best.items()):
            if count + 1 > case["max_probes"] or c + cost > case["budget"]:
                continue
            key = (covered | m, count + 1)
            cand = (c + cost, sorted(names + [name]))
            old = best.get(key)
            if old is None or (cand[0], len(cand[1]), cand[1]) < (old[0], len(old[1]), old[1]):
                best[key] = cand
    options = [(c, len(names), names) for (covered, _), (c, names) in best.items() if covered == full]
    if not options:
        return {"selected": None}
    cost, _, names = min(options)
    return {"selected": names, "cost": cost}
