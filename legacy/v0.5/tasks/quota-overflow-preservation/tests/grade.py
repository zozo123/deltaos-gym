#!/usr/bin/env python3
"""Checks candidate accounting semantics; not a proof of CPU concurrency."""
import ctypes, json, os, pathlib, random, subprocess, sys
MAX=(1<<64)-1
ROOT=pathlib.Path('/workspace'); LOGS=pathlib.Path('/logs/verifier')
LOGS.mkdir(parents=True, exist_ok=True)
REPORT={'checks':{},'passed':False}
class Budget(ctypes.Structure):
    _fields_=[('remaining',ctypes.c_uint64),('total',ctypes.c_uint64)]
def cmd(a):
    p=subprocess.run(a,text=True,capture_output=True,timeout=80)
    return p.returncode,(p.stdout+p.stderr)[-2000:]
def oracle(rem,total,amount):
    if amount>rem or amount>MAX-total: return (0,rem,total)
    return (1,rem-amount,total+amount)
def main():
    path=ROOT/'quota.c'
    if not path.is_file() or path.stat().st_size>200000:raise ValueError('Bad artifact')
    rc,log=cmd(['gcc','-std=c11','-O2','-fPIC','-shared','-Wall','-Wextra','-o','/tmp/quota.so',str(path)])
    REPORT['checks']['native_compilation']=rc==0
    if rc:raise RuntimeError(log)
    lib=ctypes.CDLL('/tmp/quota.so')
    f=lib.charge
    f.argtypes=[ctypes.POINTER(Budget),ctypes.c_uint64];f.restype=ctypes.c_int
    rng=random.Random(20261123)
    vals=[0,1,2,3,7,1024,(1<<32)-1,(1<<32),(1<<32)+1,(1<<63)-1,(1<<63),MAX-1,MAX]
    cases=[(a,b,c) for a in vals for b in vals for c in vals]
    for _ in range(18000):
        a=rng.choice(vals+[rng.getrandbits(64)])
        b=rng.choice(vals+[rng.getrandbits(64)])
        c=rng.choice(vals+[rng.getrandbits(64)])
        cases.append((a,b,c))
    failure=None
    for rem,total,amt in cases:
        state=Budget(rem,total)
        got=f(ctypes.byref(state),amt)
        want=oracle(rem,total,amt)
        if (got,state.remaining,state.total)!=want:
            failure={'initial':[rem,total],'amount':amt,'actual':[got,state.remaining,state.total],'expected':want}
            break
    REPORT['checks']['atomic_state_transition_semantics']=failure is None
    if failure:REPORT['counterexample']=failure
    else:REPORT['cases_executed']=len(cases)
    if os.environ.get('DELTAOS_SMOKE_NATIVE_ONLY')=='1':
        REPORT['checks']['bpf_bytecode_compilation']='NOT_RUN_LOCAL_SMOKE'
    else:
        rc,log=cmd(['clang','-target','bpf','-O2','-g','-I/usr/include/x86_64-linux-gnu','-c','/tests/bpf_adapter.c','-o','/tmp/quota.bpf.o'])
        REPORT['checks']['bpf_bytecode_compilation']=rc==0
        if rc:REPORT['bpf_compile_error']=log
    REPORT['passed']=all(v is True or v=='NOT_RUN_LOCAL_SMOKE' for v in REPORT['checks'].values())
if __name__=='__main__':
    try:main()
    except Exception as exc:REPORT['error']=str(exc)
    (LOGS/'reward.txt').write_text('1\n' if REPORT['passed'] else '0\n')
    (LOGS/'feedback.json').write_text(json.dumps(REPORT,indent=2)+'\n')
    print(json.dumps(REPORT,indent=2))
    sys.exit(0)
