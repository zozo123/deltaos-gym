"""Trusted reference solution using exact combinatorial optimization."""
from itertools import combinations

def select_probes(case):
    hs = case['hypotheses']
    probes = sorted(case['probes'], key=lambda p: p['name'])
    pairs = [(a,b) for i,a in enumerate(hs) for b in hs[i+1:]]
    best = None
    best_names = None
    for k in range(0, min(case['max_probes'], len(probes)) + 1):
        for indices in combinations(range(len(probes)), k):
            chosen = [probes[i] for i in indices]
            cost = sum(p['cost'] for p in chosen)
            if cost > case['budget']: continue
            if not all(any(set(p['readings'][a]).isdisjoint(p['readings'][b])
                           for p in chosen) for a,b in pairs): continue
            names = [p['name'] for p in chosen]
            key = (cost, len(chosen), names)
            if best is None or key < best:
                best, best_names = key, names
    if best is None: return {'selected': None}
    return {'selected': best_names, 'cost': best[0]}
