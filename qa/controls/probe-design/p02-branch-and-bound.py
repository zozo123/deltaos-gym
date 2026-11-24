"""Correct alternative: depth-first branch and bound over probes sorted by name."""


def select_probes(case):
    hyps = case["hypotheses"]
    probes = sorted(case["probes"], key=lambda p: p["name"])
    need = {(a, b) for i, a in enumerate(hyps) for b in hyps[i + 1:]}

    def splits(p):
        return {(a, b) for (a, b) in need if not set(p["readings"][a]) & set(p["readings"][b])}

    cover = [splits(p) for p in probes]
    best = [None]

    def visit(index, chosen, cost, covered):
        key = (cost, len(chosen), [probes[i]["name"] for i in chosen])
        if best[0] is not None and (cost, len(chosen)) > best[0][:2]:
            return
        if covered >= need:
            if best[0] is None or key < best[0]:
                best[0] = key
            return
        if index == len(probes) or len(chosen) == case["max_probes"]:
            return
        p = probes[index]
        if cost + p["cost"] <= case["budget"]:
            visit(index + 1, chosen + [index], cost + p["cost"], covered | cover[index])
        visit(index + 1, chosen, cost, covered)

    visit(0, [], 0, set())
    if best[0] is None:
        return {"selected": None}
    return {"selected": sorted(best[0][2]), "cost": best[0][0]}
