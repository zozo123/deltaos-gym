def select_probes(case):
    p=sorted(case['probes'],key=lambda p:p['cost'])
    chosen=p[:min(case['max_probes'],len(p))]
    return {'selected':sorted(x['name'] for x in chosen),'cost':sum(x['cost'] for x in chosen)}
