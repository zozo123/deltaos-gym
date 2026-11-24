#!/usr/bin/env python3
"""Runs one trusted fixture case in its own process to vary fds safely."""
import ctypes, json, os, pathlib, resource, sys, tempfile
case=json.loads(sys.stdin.read())
# Keep old-kernel close-range fallback affordable in isolated test workers.
soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE,(min(192,soft),hard))
with tempfile.TemporaryDirectory(prefix='deltaos-fd-') as temp:
    p=pathlib.Path(temp)
    pub=p/'public';secret=p/'secret';extra=p/'extra'
    pub.write_bytes(case['text'].encode())
    secret.write_bytes(b'private-credential-content')
    extra.write_bytes(b'extra-implicit-capability')
    raw_pub=os.open(str(pub),os.O_RDONLY)
    raw_sec=os.open(str(secret),os.O_RDONLY)
    tmp_pub=os.dup2(raw_pub,120,inheritable=True)
    tmp_sec=os.dup2(raw_sec,121,inheritable=True)
    # Reserve explicit public/secret slots before creating extraneous fds.
    os.dup2(tmp_pub,case['public_fd'],inheritable=case['inheritable'])
    os.dup2(tmp_sec,case['secret_fd'],inheritable=True)
    # When test target aliases a low source descriptor, use only the final
    # public/secret descriptor identities (the tmp copies remain extra fds).
    extras=[]
    for i in range(case['extras']):
        fd=os.open(str(extra),os.O_RDONLY)
        os.set_inheritable(fd,True)
        extras.append(fd)
    os.environ['DELTAOS_PUBLIC_TEXT']=case['text']
    receipt=p/'worker-executed'
    token='proof-of-exec-'+case['text']
    os.environ['DELTAOS_RECEIPT_PATH']=str(receipt)
    os.environ['DELTAOS_RECEIPT_TOKEN']=token
    lib=ctypes.CDLL(case['library'])
    run=lib.run_worker
    run.argtypes=[ctypes.c_char_p,ctypes.c_int]
    run.restype=ctypes.c_int
    result=run(case['worker'].encode(),case['public_fd'])
    good=result==0 and receipt.is_file() and receipt.read_text()==token
    try:
        for fd in [case['public_fd'],case['secret_fd'],*extras]:
            os.fstat(fd)
    except OSError:
        good=False
    print(json.dumps({'ok':good,'exit_status':result,'public_fd':case['public_fd'],'secret_fd':case['secret_fd'],'cloexec':not case['inheritable'],'extra_count':case['extras']}))
