"""Candidate implementation: deliberately wrong.

Choosing every probe is wasteful and can still be unable to distinguish
hypotheses when event streams overlap.
"""
def select_probes(case: dict) -> dict:
    names = sorted(p['name'] for p in case['probes'])
    return {'selected': names, 'cost': sum(p['cost'] for p in case['probes'])}
