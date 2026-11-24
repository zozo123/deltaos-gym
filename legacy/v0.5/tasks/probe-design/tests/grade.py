#!/usr/bin/env python3
"""Independent exhaustive oracle for finite active-probe selection."""
import itertools, json, os, pathlib, random, subprocess, sys
ROOT=pathlib.Path(os.environ.get('DELTAOS_WORKSPACE','/workspace'))
TESTS=pathlib.Path(os.environ.get('DELTAOS_TESTS','/tests'))
LOGS=pathlib.Path(os.environ.get('DELTAOS_LOGS','/logs/verifier'))
LOGS.mkdir(parents=True,exist_ok=True)

def oracle(c):
    hs=c['hypotheses'];ps=sorted(c['probes'],key=lambda p:p['name'])
    pairs=[(a,b) for i,a in enumerate(hs) for b in hs[i+1:]]
    best=None
    for k in range(min(len(ps),c['max_probes'])+1):
        for subset in itertools.combinations(ps,k):
            cost=sum(p['cost'] for p in subset)
            if cost>c['budget']: continue
            distinguish=all(any(not(set(p['readings'][a]) & set(p['readings'][b]))
                                for p in subset) for a,b in pairs)
            if distinguish:
                names=sorted(p['name'] for p in subset)
                key=(cost,k,names)
                if best is None or key<best:best=key
    return {'selected': None} if best is None else {'selected':best[2], 'cost':best[0]}

def generate():
    rng=random.Random(379114)
    fixed=[
        {'hypotheses':['a','b'],'budget':5,'max_probes':2,
         'probes':[{'name':'eBPF','cost':3,'readings':{'a':[0,1],'b':[1,2]}},
                   {'name':'ptrace','cost':4,'readings':{'a':[0],'b':[1]}}]},
        {'hypotheses':['a','b'],'budget':2,'max_probes':1,
         'probes':[{'name':'only','cost':2,'readings':{'a':[1,2],'b':[2,3]}}]},
        {'hypotheses':['a','b','c'],'budget':7,'max_probes':1,
         'probes':[{'name':'all_one','cost':1,'readings':{'a':[0],'b':[0],'c':[0]}},
                   {'name':'pair_a','cost':2,'readings':{'a':[0],'b':[1],'c':[1]}},
                   {'name':'pair_b','cost':2,'readings':{'a':[1],'b':[0],'c':[1]}}]},
    ]
    for i in range(290):
        m=rng.randint(2,7)
        n=rng.randint(3,11)
        hs=['h'+str(j) for j in range(m)]
        ps=[]
        for j in range(n):
            readings={}
            for h in hs:
                v=rng.randrange(5)
                readings[h]=[v] if rng.random()<0.56 else sorted({v,(v+rng.choice([1,2,3]))%5})
            ps.append({'name':'probe_'+str(j).zfill(2), 'cost':rng.randrange(1,12),'readings':readings})
        budget=rng.randint(2,33)
        fixed.append({'hypotheses':hs,'budget':budget,'max_probes':rng.randint(1,min(7,n)),'probes':ps})
    return fixed

def main():
    result={'passed':False,'checks':{},'assurance':'EXHAUSTIVE_FINITE_MODEL', 'cases':0}
    try:
        path=ROOT/'solver.py'
        if not path.is_file() or path.stat().st_size>200000:raise ValueError('missing or oversized solver')
        cases=generate()
        p=subprocess.run([sys.executable,str(TESTS/'runner.py'),str(path)],input=json.dumps(cases),text=True,capture_output=True,timeout=65,cwd='/tmp')
        if p.returncode:raise ValueError('candidate error: '+p.stderr[-1000:])
        results=json.loads(p.stdout)
        if len(results)!=len(cases):raise ValueError('incorrect number of answers')
        for index,(case,got) in enumerate(zip(cases,results)):
            want=oracle(case)
            if got!=want:
                result['counterexample']={'index':index,'expected':want,'actual':got,'task':case}
                result['cases']=index+1
                break
            result['cases']+=1
        else:
            result['passed']=True
            result['checks']['cost_optimality']=True
            result['checks']['observation_soundness']=True
    except Exception as e:result['error']=str(e)
    (LOGS/'reward.txt').write_text('1\n' if result['passed'] else '0\n')
    (LOGS/'feedback.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'cases':result['cases'], 'error':result.get('error'), 'counterexample':result.get('counterexample',{}).get('index')}))
if __name__=='__main__':main()
