#!/usr/bin/env python3
"""Independent actual-Linux fork/exec tests for descriptor confinement."""
import json, os, pathlib, random, subprocess, sys, tempfile
ROOT=pathlib.Path(os.environ.get('DELTAOS_WORKSPACE','/workspace'))
TESTS=pathlib.Path(os.environ.get('DELTAOS_TESTS','/tests'))
LOGS=pathlib.Path(os.environ.get('DELTAOS_LOGS','/logs/verifier'))
LOGS.mkdir(parents=True,exist_ok=True)

def main():
    report={'passed':False,'checks':{},'cases':0,'assurance':'LIVE_LINUX_SYSCALL_TESTED'}
    try:
        p=ROOT/'spawn.c'
        if not p.is_file() or p.stat().st_size>200000:raise ValueError('missing/oversize spawn.c')
        with tempfile.TemporaryDirectory(prefix='deltaos-build-') as tmp:
            tmp=pathlib.Path(tmp);lib=tmp/'spawn.so';worker=tmp/'worker'
            cmds=[['gcc','-std=c11','-O2','-Wall','-Wextra','-shared','-fPIC', '-I'+str(ROOT), str(p),'-o',str(lib)],
                  ['gcc','-std=c11','-O2','-Wall','-Wextra', str(TESTS/'worker.c'),'-o',str(worker)]]
            for cmd in cmds:
                z=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
                if z.returncode:raise RuntimeError('compile error: '+z.stderr[-1500:])
            report['checks']['native_compilation']=True
            rng=random.Random(102942)
            cases=[]
            for fd in (3,5,8,11):
                for secret in (4,6,10,14):
                    if fd==secret:continue
                    for inheritable in (False,True):
                        for extras in (0,5):
                            cases.append({'public_fd':fd,'secret_fd':secret,'inheritable':inheritable,
                                          'extras':extras,'text':'public-task-payload-'+str(rng.getrandbits(64))})
            rng.shuffle(cases)
            # 24 distinct real fork/exec trials keep CI latency bounded.
            # Include explicit cases for the fd=3 CLOEXEC trap and high-fd leaks.
            mandatory=[{'public_fd':3,'secret_fd':4,'inheritable':False,'extras':5},
                       {'public_fd':3,'secret_fd':6,'inheritable':True,'extras':0},
                       {'public_fd':8,'secret_fd':10,'inheritable':False,'extras':5},
                       {'public_fd':11,'secret_fd':14,'inheritable':True,'extras':5}]
            chosen=[]
            for spec in mandatory:
                chosen.append(next(c for c in cases if all(c[k]==v for k,v in spec.items())))
            chosen+= [c for c in cases if c not in chosen][:20]
            cases=chosen
            for idx,case in enumerate(cases):
                case['library']=str(lib);case['worker']=str(worker)
                z=subprocess.run([sys.executable,str(TESTS/'case_runner.py')],input=json.dumps(case),capture_output=True,text=True,timeout=4)
                if z.returncode:
                    report['counterexample']={'index':idx,'reason':'runner failure','details':z.stderr[-650:], 'case':{k:v for k,v in case.items() if k not in ('library','worker')}}
                    break
                try:answer=json.loads(z.stdout)
                except Exception:
                    report['counterexample']={'index':idx,'reason':'invalid runner output','output':z.stdout[-400:]}
                    break
                report['cases']=idx+1
                if not answer['ok']:
                    report['counterexample']=answer
                    break
            else:
                report['passed']=True
                report['checks']['post_exec_fd_confinement']=True
                report['checks']['parent_fd_preservation']=True
    except Exception as e:report['error']=str(e)
    (LOGS/'reward.txt').write_text('1\n' if report['passed'] else '0\n')
    (LOGS/'feedback.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
