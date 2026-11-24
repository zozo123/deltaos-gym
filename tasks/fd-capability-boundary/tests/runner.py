#!/usr/bin/env python3
"""The caller in one fd-capability-boundary case.

A fresh copy of this process is started for every case, as the sandbox user.
Up to the "go" message it is this trusted file running alone: it builds the
descriptor layout the grader asked for and says "ready". After "go" it loads the
candidate library, and from then on the process belongs to the candidate.
The grader therefore believes nothing this process says about itself: it reads
this process's descriptor table from /proc, and the worker's own receipt.

Messages are single JSON lines on two pipes parked at high descriptor numbers,
so whatever the candidate prints to descriptors 0, 1 and 2 means nothing.

  runner.py INHERITED_IN INHERITED_OUT CONTROL_IN CONTROL_OUT
"""
import ctypes
import fcntl
import json
import os
import resource
import signal
import socket
import sys


def send(fd, message):
    os.write(fd, (json.dumps(message) + "\n").encode())


def receive(fd):
    data = b""
    while not data.endswith(b"\n"):
        chunk = os.read(fd, 65536)
        if not chunk:
            return None
        data += chunk
    return json.loads(data)


def build_layout(objects, stage_base):
    """Open every object, then place each of its descriptors at the exact number asked for."""
    staged = []
    for item in objects:
        kind = item["kind"]
        if kind == "file":
            opened = [os.open(item["path"], os.O_RDONLY)]
            os.lseek(opened[0], item.get("offset", 0), os.SEEK_SET)
        elif kind == "dir":
            opened = [os.open(item["path"], os.O_RDONLY | os.O_DIRECTORY)]
        elif kind == "pipe":
            opened = list(os.pipe())
        elif kind == "socketpair":
            opened = [end.detach() for end in socket.socketpair()]
        else:
            raise ValueError("unknown object kind: %r" % (kind,))
        parked = []
        for fd in opened:                       # out of the way of every target number
            parked.append(fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, stage_base))
            os.close(fd)
        staged.append((item, parked))
    for item, parked in staged:
        for slot in item["slots"]:
            os.dup2(parked[slot.get("end", 0)], slot["fd"], inheritable=not slot["cloexec"])
    for _, parked in staged:
        for fd in parked:
            os.close(fd)


def trusted_launch(worker, fd, limit, fault):
    """The grader's own launcher, used to check its instruments before any candidate runs.

    fault: None (correct), "leak" (closes nothing), "clobber" (does the plumbing in
    the caller), "no_retry" (one waitpid, no EINTR retry).
    """
    if fault == "clobber" and fd != 3:
        os.dup2(fd, 3, inheritable=True)
    pid = os.fork()
    if pid == 0:
        try:
            if fd != 3:
                os.dup2(fd, 3, inheritable=True)
            else:
                os.set_inheritable(3, True)
            if fault != "leak":
                os.closerange(4, limit)
            os.execv(worker, [worker])
        finally:
            os._exit(127)
    if fault == "no_retry":
        status = ctypes.c_int(0)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.waitpid(pid, ctypes.byref(status), 0) != pid:
            return -1
        return os.waitstatus_to_exitcode(status.value)
    _, status = os.waitpid(pid, 0)              # retried on EINTR by Python (PEP 475)
    return os.waitstatus_to_exitcode(status)


def main():
    inherited_in, inherited_out, control_in, control_out = (int(arg) for arg in sys.argv[1:5])
    os.dup2(inherited_in, control_in, inheritable=False)
    os.dup2(inherited_out, control_out, inheritable=False)
    os.close(inherited_in)
    os.close(inherited_out)

    alarms = [0]

    def on_alarm(signum, frame):
        alarms[0] += 1

    try:
        setup = receive(control_in)
        build_layout(setup["objects"], setup["stage_base"])
        if setup.get("soft_nofile"):
            hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            resource.setrlimit(resource.RLIMIT_NOFILE, (setup["soft_nofile"], hard))
    except Exception as exc:                    # the environment, not the candidate
        send(control_out, {"error": "%s: %s" % (type(exc).__name__, exc)})
        return 2
    send(control_out, {"ready": True, "pid": os.getpid()})
    if receive(control_in) is None:
        return 2

    # ---- from here on the candidate's code may be running in this process
    launcher = setup["launcher"]
    worker, fd = setup["worker"], setup["authorized_fd"]
    function = None
    if launcher["mode"] == "library":
        try:
            library = ctypes.CDLL(launcher["path"])
            function = library.run_worker
            function.argtypes = [ctypes.c_char_p, ctypes.c_int]
            function.restype = ctypes.c_int
        except (OSError, AttributeError) as exc:
            send(control_out, {"load_error": "%s: %s" % (type(exc).__name__, exc)})
            return 3
    if setup.get("alarm_seconds"):
        signal.signal(signal.SIGALRM, on_alarm)     # Python installs it without SA_RESTART
        signal.setitimer(signal.ITIMER_REAL, setup["alarm_seconds"], setup["alarm_seconds"])
    if function is not None:
        returned = function(worker.encode(), fd)
    else:
        returned = trusted_launch(worker, fd, setup["nofile"], launcher.get("fault"))
    signal.setitimer(signal.ITIMER_REAL, 0, 0)
    send(control_out, {"returned": returned, "alarms": alarms[0]})
    receive(control_in)                             # stay as we are until the grader has looked
    return 0


if __name__ == "__main__":
    sys.exit(main())
