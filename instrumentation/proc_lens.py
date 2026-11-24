#!/usr/bin/env python3
"""Unprivileged, best-effort Linux process observability.

Collects stable, scoped evidence rather than assuming traces are complete.
Use only with processes you have permission to inspect. Never treats missing
observations as proof that no corresponding kernel event occurred.
"""
import argparse, json, os, pathlib, platform, time

def _read(path):
    try:return pathlib.Path(path).read_text(errors='replace')
    except (OSError,PermissionError) as e:return None

def _pairs(text):
    if text is None:return None
    d={}
    for line in text.splitlines():
        k,sep,v=line.partition(':')
        if sep:d[k.strip()]=v.strip()
    return d

def observe(pid):
    root=pathlib.Path('/proc')/str(int(pid))
    now=time.time_ns()
    status=_pairs(_read(root/'status'))
    io=_pairs(_read(root/'io'))
    sched=_read(root/'schedstat')
    files=[]
    errors=[]
    try:
        for item in sorted((root/'fd').iterdir(),key=lambda p:int(p.name)):
            try:
                entry={'fd':int(item.name),'target':os.readlink(item)}
                info=_pairs(_read(root/'fdinfo'/item.name))
                if info and 'flags' in info:
                    flags=int(info['flags'],8)
                    entry['flags_octal']=info['flags']
                    entry['cloexec']=bool(flags & 0o2000000)
                    entry['pos']=int(info.get('pos','0'))
                files.append(entry)
            except OSError as e:errors.append({'fd':item.name,'error':type(e).__name__})
    except OSError as e:errors.append({'fd_directory_error':type(e).__name__})
    children=[]
    try:
        for task in (root/'task').iterdir():
            text=_read(task/'children')
            if text:children+=[int(x) for x in text.split()]
    except OSError as e:errors.append({'children_error':type(e).__name__})
    return {
      'clock_ns':now,
      'kernel_release':platform.release(),
      'pid':int(pid),
      'status':{k:status.get(k) for k in ('State','Threads','VmRSS','voluntary_ctxt_switches','nonvoluntary_ctxt_switches')} if status else None,
      'io':{k:io.get(k) for k in ('rchar','wchar','syscr','syscw','read_bytes','write_bytes')} if io else None,
      'schedstat':sched.strip().split() if sched else None,
      'open_fd_count':len(files),
      'children':sorted(set(children)),
      'fds':files,
      'capture_errors':errors,
      'assurance':'best_effort_procfs_snapshot_not_complete_event_trace'
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pid',type=int,default=os.getpid())
    p.add_argument('--interval-ms',type=int,default=0)
    p.add_argument('--samples',type=int,default=1)
    args=p.parse_args()
    if args.samples<1 or args.samples>1000:raise SystemExit('samples must be 1..1000')
    for i in range(args.samples):
        if i and args.interval_ms:time.sleep(args.interval_ms/1000)
        print(json.dumps(observe(args.pid)),flush=True)
if __name__=='__main__':main()
