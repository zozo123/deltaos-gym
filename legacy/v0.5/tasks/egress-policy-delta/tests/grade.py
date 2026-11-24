#!/usr/bin/env python3
"""Independent dynamic semantics + eBPF bytecode compilation.

This is not a proof of Linux kernel verifier acceptance, nor a semantic
proof over the full 2^32 IPv4 space. In production run in disposable VMs.
"""
import ctypes, json, os, pathlib, random, subprocess, sys

ROOT = pathlib.Path('/workspace')
LOGS = pathlib.Path('/logs/verifier')
LOGS.mkdir(parents=True, exist_ok=True)
REPORT = {'checks': {}, 'passed': False}

def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=80)
    return p.returncode, (p.stdout+p.stderr)[-2000:]

def expected(uid, ip, port, proto, prior):
    return int(bool(prior) or (uid == 10042 and ip == 0x0a040209 and port == 443 and proto == 6))

def main():
    source = ROOT/'policy.c'
    if not source.is_file() or source.stat().st_size > 200000:
        raise ValueError('Missing or oversized source artifact')
    rc, log = command(['gcc','-std=c11','-O2','-fPIC','-shared','-Wall','-Wextra',
                       '-o','/tmp/candidate.so',str(source)])
    REPORT['checks']['native_compilation'] = (rc == 0)
    if rc: raise RuntimeError('Native compile: '+log)
    lib = ctypes.CDLL('/tmp/candidate.so')
    fn = lib.policy_decide
    fn.argtypes = [ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint16,
                   ctypes.c_uint32,ctypes.c_uint32]
    fn.restype = ctypes.c_int
    rng = random.Random(78192)  # private to the verifier image
    cases = []
    for prior in (0,1):
        for uid in (10042,10043,0,0xffffffff):
            for ip in (0x0a040209,0x0a040208,0x0a04020a,0x0a040200,
                       0x0a0402ff,0x7f000001,0xffffffff,0):
                for port in (0,53,80,443,444,65535):
                    for proto in (6,17,0,255):
                        cases.append((uid,ip,port,proto,prior))
    for _ in range(25000):
        prior = rng.randrange(2)
        uid = rng.choice([10042,10043,0xffffffff,rng.getrandbits(32)])
        ip = rng.choice([0x0a040209,0x0a040208,0x0a0402ff,rng.getrandbits(32)])
        port = rng.choice([443,53,80,rng.randrange(65536)])
        proto = rng.choice([6,17,rng.randrange(256)])
        cases.append((uid,ip,port,proto,prior))
    failure = None
    for case in cases:
        actual = fn(*case)
        want = expected(*case)
        if actual != want:
            failure = {'case': case, 'expected': want, 'actual': actual}
            break
    REPORT['checks']['native_semantics'] = failure is None
    REPORT['cases_executed'] = len(cases) if failure is None else None
    if failure: REPORT['counterexample'] = failure
    # A local smoke run has no BPF-target compiler; do not use this bypass
    # in production. The Harbor verifier's environment does not set it.
    if os.environ.get('DELTAOS_SMOKE_NATIVE_ONLY') == '1':
        REPORT['checks']['bpf_bytecode_compilation'] = 'NOT_RUN_LOCAL_SMOKE'
    else:
        rc, log = command(['clang','-target','bpf','-O2','-g',
                           '-I/usr/include/x86_64-linux-gnu',
                           '-c','/tests/bpf_adapter.c','-o','/tmp/policy.bpf.o'])
        REPORT['checks']['bpf_bytecode_compilation'] = rc == 0
        if rc: REPORT['bpf_compile_error'] = log
    REPORT['passed'] = all(v is True or v == 'NOT_RUN_LOCAL_SMOKE'
                           for v in REPORT['checks'].values())

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        REPORT['error'] = str(exc)
    (LOGS/'reward.txt').write_text('1\n' if REPORT['passed'] else '0\n')
    (LOGS/'feedback.json').write_text(json.dumps(REPORT,indent=2)+'\n')
    print(json.dumps(REPORT,indent=2))
    sys.exit(0)  # Harbor reads reward.txt, not process exit status
