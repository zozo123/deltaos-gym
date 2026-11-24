#!/usr/bin/env python3
"""Grader for fd-capability-boundary: real fork/exec on Linux, observed from outside.

Three identities when the grader runs as root:
  root            this grader
  sandbox uid     the caller: runner.py loads the candidate library and calls run_worker()
  observer uid    the worker (worker.c), installed setuid to this uid and execute-only

Only by really exec'ing the worker can anything appear in the receipts directory, which
belongs to the observer uid. The worker writes down the descriptor table it got and
what it read from descriptor 3. The caller's own table is read from /proc before and
after the call. The candidate's process is never asked whether it did the right thing.
"""
import json
import os
import pathlib
import re
import secrets
import select
import signal
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/fd-capability-boundary"
MODEL = "linux-fork-exec/2"
CONTROL_IN, CONTROL_OUT = 1020, 1021
NOFILE = 1024
READ_BYTES = 32


class Violation(Exception):
    def __init__(self, reason, **detail):
        super().__init__(reason)
        self.detail = {"reason": reason, **detail}


def _read_table(pid):
    table = {}
    base = f"/proc/{pid}"
    for name in os.listdir(f"{base}/fd"):
        target = os.readlink(f"{base}/fd/{name}")
        info = pathlib.Path(f"{base}/fdinfo/{name}").read_text()
        flags = re.search(r"flags:\s*([0-7]+)", info)
        pos = re.search(r"pos:\s*(\d+)", info)
        if not flags or not pos:
            raise OSError("unreadable fdinfo")
        table[int(name)] = (target, int(flags.group(1), 8), int(pos.group(1)))
    return table


def fd_table(pid, sbx):
    """The caller's descriptor table, read from /proc.

    Root in a container usually lacks CAP_SYS_PTRACE and cannot read another user's
    descriptor links, so as root a short-lived helper switches to the caller's own uid.
    A caller that makes itself unreadable (PR_SET_DUMPABLE 0) is treated as hiding."""
    if not sbx.separated:
        return _read_table(pid)
    read_end, write_end = os.pipe()
    helper = os.fork()
    if helper == 0:
        try:
            os.close(read_end)
            os.setgroups([])
            os.setgid(sbx.gid)
            os.setuid(sbx.uid)
            data = json.dumps({"table": {str(k): list(v) for k, v in _read_table(pid).items()}})
        except Exception as exc:
            data = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        try:
            view = memoryview(data.encode())
            while view:
                view = view[os.write(write_end, view):]
        finally:
            os._exit(0)
    os.close(write_end)
    chunks = []
    while True:
        chunk = os.read(read_end, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_end)
    os.waitpid(helper, 0)
    answer = json.loads(b"".join(chunks) or b'{"error": "no answer"}')
    if "error" in answer:
        raise Violation("the_callers_descriptor_table_could_not_be_read", error=answer["error"])
    return {int(k): tuple(v) for k, v in answer["table"].items()}


def children(pid):
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = pathlib.Path(f"/proc/{entry}/stat").read_text()
        except OSError:
            continue
        rest = stat[stat.rindex(")") + 2:].split()
        if int(rest[1]) == pid:
            found.append({"pid": int(entry), "state": rest[0]})
    return found


def parse_receipt(text):
    out = {"fds": {}}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "fd":
            target = bytes.fromhex(parts[4]).decode("utf-8", "replace") if len(parts) > 4 else ""
            out["fds"][int(parts[1])] = {"cloexec": int(parts[2]), "target": target}
        elif key in ("nonce", "case", "start", "ruid", "euid"):
            out[key] = parts[1]
        elif key == "listed":
            out["listed"] = [int(x) for x in parts[1:4]]
        elif key == "fd3_stat":
            out["fd3_stat"] = [int(parts[1]), int(parts[2]), int(parts[3])]
        elif key == "fd3_offset":
            out["fd3_offset"] = [int(parts[1]), int(parts[2])]
        elif key == "fd3_read":
            out["fd3_read"] = [int(parts[1]), bytes.fromhex(parts[3]) if len(parts) > 3 else b""]
        elif key == "end":
            out["complete"] = True
    return out


class Lab:
    """Files, the trusted worker and the receipts directory for one grading run."""

    def __init__(self, ctx):
        self.ctx, self.sbx = ctx, ctx.sandbox
        self.root_mode = self.sbx.separated
        self.observer = int(os.environ.get("DELTAOS_OBSERVER_UID", "65533")) if self.root_mode else os.getuid()
        self.nonce = secrets.token_hex(16)
        base = self.sbx.root
        self.files = base / "files"
        self.bin = base / "bin"
        self.receipts = base / "receipts"
        for path in (self.files, self.bin):
            path.mkdir(mode=0o711)
        self.receipts.mkdir(mode=0o700)
        if self.root_mode:
            os.chown(self.receipts, self.observer, self.observer)
        self.worker = self.bin / "worker"
        flags = [f'-DRECEIPT_DIR="{self.receipts}"', f'-DRUN_NONCE="{self.nonce}"']
        built = None
        for extra in (["-static"], []):
            built = subprocess.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", *extra, *flags,
                                    str(H.TESTS / "worker.c"), "-o", str(self.worker)],
                                   capture_output=True, text=True, timeout=120)
            if built.returncode == 0:
                break
        if built.returncode:
            raise H.GraderError("worker.c did not build: " + built.stderr[-800:])
        if self.root_mode:
            os.chown(self.worker, self.observer, self.observer)
            os.chmod(self.worker, 0o4711)
        self.counter = 0

    def file(self, data: bytes) -> pathlib.Path:
        self.counter += 1
        path = self.files / f"f{self.counter}"
        path.write_bytes(data)
        os.chmod(path, 0o644)
        return path

    def directory(self) -> pathlib.Path:
        self.counter += 1
        path = self.files / f"d{self.counter}"
        path.mkdir(mode=0o755)
        return path

    def reset_receipts(self):
        for item in self.receipts.iterdir():
            item.unlink()

    def write_case(self, case_id, info, offset, exit_code, kill_signal, sleep_ms):
        data = struct.pack("<8s32sQQQQIIIIII", b"DOSCASE1", self.nonce.encode(), case_id, info.st_dev,
                           info.st_ino, offset, READ_BYTES, exit_code, kill_signal, 0, 0, sleep_ms)
        path = self.receipts / "case"
        path.write_bytes(data)
        if self.root_mode:
            os.chown(path, self.observer, self.observer)
        os.chmod(path, 0o400)

    def receipt(self, name):
        path = self.receipts / name
        return path.read_text() if path.is_file() else None


def plan(rng):
    """Regression cases, then cases drawn fresh for this episode."""
    cases = [
        {"auth": 3, "cloexec": True, "extras": 5, "behaviour": "exit0"},
        {"auth": 3, "cloexec": False, "extras": 0, "behaviour": "exit0"},
        {"auth": 8, "cloexec": True, "extras": 5, "high": True, "behaviour": "exit0"},
        {"auth": 57, "cloexec": False, "extras": 4, "behaviour": "exit0"},
        {"auth": 5, "cloexec": False, "extras": 3, "behaviour": "exit_code"},
        {"auth": 11, "cloexec": True, "extras": 3, "behaviour": "signal"},
        {"auth": 8, "cloexec": False, "extras": 2, "behaviour": "slow"},
        {"auth": 5, "cloexec": False, "extras": 2, "behaviour": "bad_fd"},
        {"auth": 3, "cloexec": False, "extras": 2, "behaviour": "missing_worker"},
    ]
    behaviours = ["exit0"] * 6 + ["exit_code", "signal", "slow", "bad_fd", "missing_worker"]
    for _ in range(15):
        cases.append({"auth": rng.choice([3, 5, 8, 11, 57, rng.randint(4, 200)]), "cloexec": rng.random() < 0.5,
                      "extras": rng.randint(0, 7), "high": rng.random() < 0.4,
                      "behaviour": rng.choice(behaviours)})
    return cases


def layout(lab, rng, case):
    """Objects for runner.py to place, and what the worker should find at descriptor 3."""
    used = {0, 1, 2, CONTROL_IN, CONTROL_OUT, case["auth"]}
    content = bytes(rng.randrange(256) for _ in range(400))
    offset = rng.randint(0, 200)
    authorized = lab.file(content)
    objects = [{"kind": "file", "path": str(authorized), "offset": offset,
                "slots": [{"fd": case["auth"], "cloexec": case["cloexec"]}]}]
    if case["auth"] != 3:
        used.add(3)
        objects.append({"kind": "file", "path": str(lab.file(b"decoy secret, not for the worker")),
                        "slots": [{"fd": 3, "cloexec": False}]})

    def free_fd(low, high):
        while True:
            fd = rng.randint(low, high)
            if fd not in used:
                used.add(fd)
                return fd

    for index in range(case["extras"]):
        kind = rng.choice(["file", "dir", "pipe", "socketpair"])
        high = case.get("high") and index == 0
        pick = (lambda: free_fd(256, 900)) if high else (lambda: free_fd(4, 300))
        inheritable_or_not = lambda: rng.random() < 0.3
        if kind in ("pipe", "socketpair"):
            slots = [{"fd": pick(), "cloexec": inheritable_or_not(), "end": 0},
                     {"fd": pick(), "cloexec": inheritable_or_not(), "end": 1}]
            objects.append({"kind": kind, "slots": slots})
        else:
            path = lab.directory() if kind == "dir" else lab.file(b"another capability")
            objects.append({"kind": kind, "path": str(path), "slots": [{"fd": pick(), "cloexec": inheritable_or_not()}]})
    if case["behaviour"] == "bad_fd":
        objects = objects[1:]           # the authorized descriptor number is not open at all
    return objects, authorized, content, offset


class Channel:
    def __init__(self, read_fd, write_fd):
        self.read_fd, self.write_fd, self.buffer = read_fd, write_fd, b""

    def send(self, message):
        try:
            os.write(self.write_fd, (json.dumps(message) + "\n").encode())
        except OSError:
            raise Violation("the_caller_process_died")

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.read_fd], [], [], left)[0]:
                return None
            chunk = os.read(self.read_fd, 65536)
            if not chunk:
                return None
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        try:
            return json.loads(line)
        except ValueError:
            return {"garbled": line[:200].decode("latin-1")}


def run_case(ctx, lab, library, rng, index, case):
    sbx = ctx.sandbox
    lab.reset_receipts()
    objects, authorized, content, offset = layout(lab, rng, case)
    info = os.stat(authorized)
    behaviour = case["behaviour"]
    exit_code = rng.randint(1, 120) if behaviour == "exit_code" else 0
    kill_signal = rng.choice([signal.SIGTERM, signal.SIGKILL, signal.SIGUSR1]) if behaviour == "signal" else 0
    lab.write_case(index, info, offset, exit_code, kill_signal, 300 if behaviour == "slow" else 0)
    worker = str(lab.worker) if behaviour != "missing_worker" else str(lab.bin / "no-such-worker")

    to_runner_r, to_runner_w = os.pipe()
    from_runner_r, from_runner_w = os.pipe()
    stderr_path = sbx.io / f"runner{index}.err"
    with open(stderr_path, "wb") as stderr:
        proc = sbx.popen(["python3", "-I", str(sbx.path("runner.py")), str(to_runner_r), str(from_runner_w),
                          str(CONTROL_IN), str(CONTROL_OUT)],
                         pass_fds=(to_runner_r, from_runner_w), allow_privilege_gain=True,
                         limits={"cpu": 30, "as": 2048 * H.MiB, "fsize": 64 * H.MiB, "nofile": NOFILE},
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr)
    os.close(to_runner_r)
    os.close(from_runner_w)
    channel = Channel(from_runner_r, to_runner_w)
    summary = {"case": index, "authorized_fd": case["auth"], "behaviour": behaviour,
               "authorized_cloexec": case["cloexec"]}
    try:
        channel.send({"objects": objects, "stage_base": 940, "worker": worker, "authorized_fd": case["auth"],
                      "launcher": {"mode": "library", "path": str(library)}, "nofile": NOFILE,
                      "soft_nofile": NOFILE, "alarm_seconds": 0.004 if behaviour == "slow" else 0})
        ready = channel.receive(20)
        if not ready or not ready.get("ready"):
            raise H.GraderError("the caller could not set up the layout: " + json.dumps(ready)[:300] +
                                stderr_path.read_text(errors="replace")[-400:])
        pid = ready["pid"]
        before = fd_table(pid, sbx)
        channel.send({"go": True})
        answer = channel.receive(20)
        if answer is None:
            raise Violation("the_caller_died_or_hung_inside_run_worker", **summary)
        if "load_error" in answer:
            raise Violation("library_does_not_load", error=answer["load_error"])
        if "returned" not in answer:
            raise Violation("the_caller_did_not_report_a_return_value", **summary)
        returned = answer["returned"]
        after = fd_table(pid, sbx)
        kids = children(pid)
        finished = lab.receipt("finished.0")
        observed = lab.receipt("observed.0")
        second = lab.receipt("observed.1")
        channel.send({"done": True})
    finally:
        os.close(from_runner_r)
        os.close(to_runner_w)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        sbx.kill_all()
        proc.wait()

    # The caller's own table must be exactly as it was, apart from the authorized
    # descriptor's offset, which the worker moved by reading through the shared file.
    if set(before) != set(after):
        raise Violation("the_caller_lost_or_gained_descriptors", **summary,
                        lost=sorted(set(before) - set(after)), gained=sorted(set(after) - set(before)))
    for fd in before:
        if before[fd][:2] != after[fd][:2]:
            raise Violation("the_caller_descriptor_changed", **summary, fd=fd,
                            before={"target": before[fd][0], "flags": oct(before[fd][1])},
                            after={"target": after[fd][0], "flags": oct(after[fd][1])})
    if kids:
        raise Violation("the_worker_was_not_reaped", **summary, children=kids)

    if behaviour in ("bad_fd", "missing_worker"):
        if returned == 0:
            raise Violation("success_reported_although_the_worker_could_not_run_as_asked", **summary)
        return "failure reported"
    if observed is None or finished is None:
        raise Violation("the_worker_never_ran" if observed is None else "run_worker_returned_before_the_worker_finished",
                        **summary, returned=returned)
    if second is not None:
        raise Violation("the_worker_was_started_twice", **summary)
    seen = parse_receipt(observed)
    if not seen.get("complete") or seen.get("nonce") != lab.nonce or seen.get("case") != str(index):
        raise Violation("unreadable_receipt", **summary)
    if lab.root_mode and seen.get("euid") != str(lab.observer):
        raise Violation("the_receipt_was_not_written_by_the_trusted_worker", **summary)
    fds = sorted(seen["fds"])
    if seen["listed"][1] != len(fds) or not set(fds) <= {0, 1, 2, 3}:
        raise Violation("descriptors_leaked_into_the_worker", **summary,
                        leaked={fd: seen["fds"][fd]["target"] for fd in fds if fd > 3})
    stat_errno, dev, ino = seen["fd3_stat"]
    if 3 not in seen["fds"] or stat_errno or (dev, ino) != (info.st_dev, info.st_ino):
        raise Violation("descriptor_3_is_not_the_authorized_file", **summary,
                        worker_saw=seen["fds"].get(3, {}).get("target", "nothing at descriptor 3"))
    if seen["fd3_offset"] != [0, offset] or seen["fd3_read"][1] != content[offset:offset + READ_BYTES]:
        raise Violation("descriptor_3_is_not_the_same_open_file", **summary,
                        expected_offset=offset, worker_offset=seen["fd3_offset"][1])
    auth = case["auth"]
    if after[auth][2] != before[auth][2] + READ_BYTES:
        raise Violation("descriptor_3_is_a_reopened_copy_not_the_callers_open_file", **summary)
    if behaviour == "exit0" and returned != 0:
        raise Violation("failure_reported_although_the_worker_succeeded", **summary, returned=returned)
    if behaviour == "slow":
        if returned != 0:
            raise Violation("interrupted_by_a_signal_and_reported_failure", **summary, returned=returned,
                            alarms=answer.get("alarms"))
        if not answer.get("alarms"):
            raise H.GraderError("no SIGALRM reached the caller during the slow case")
    if behaviour in ("exit_code", "signal") and returned == 0:
        raise Violation("success_reported_although_the_worker_failed", **summary,
                        worker_exit=exit_code or f"killed by signal {int(kill_signal)}")
    return "ok"


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    if not H.LINUX:
        raise H.GraderError("this task needs Linux: it runs real fork/exec and reads /proc")
    source = H.read_artifact("spawn.c")
    receipt.artifact("spawn.c", source)
    sbx.put("spawn.c", source)
    sbx.put("spawn.h", (H.TESTS / "spawn.h").read_bytes())
    sbx.put("runner.py", (H.TESTS / "runner.py").read_bytes())
    ctx.require_tool("gcc", "launches")
    build = sbx.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-shared", "-fPIC", "-iquote", ".", "spawn.c", "-o",
                     "libspawn.so"], limits=H.TOOL_LIMITS, timeout=60)
    receipt.check("compiles", build.ok)
    if not build.ok:
        raise H.Reject("does_not_compile", log=build.text(1200))
    library = sbx.path("libspawn.so")
    lab = Lab(ctx)
    receipt.isolation["observer"] = ("setuid worker under uid %d, receipts directory owned by it" % lab.observer
                                     if lab.root_mode else "same uid: a candidate could forge receipts")
    rng = ctx.rng("layouts")
    outcomes = []
    try:
        for index, case in enumerate(plan(rng)):
            outcomes.append(run_case(ctx, lab, library, rng, index, case))
    except Violation as violation:
        receipt.check("launches", False)
        raise H.Reject(**violation.detail)
    receipt.check("launches", True)
    receipt.extra["cases_executed"] = len(outcomes)
    scope = (f"{len(outcomes)} real launches on Linux {H.platform.release()}: authorized descriptor at 3, 5, 8, 11, 57 "
             "and random numbers, with and without close-on-exec, a decoy at descriptor 3, files, directories, "
             "pipes and sockets up to descriptor 900; workers that exit 0, exit non-zero, die from a signal or "
             "run slowly while SIGALRM interrupts the caller; a closed authorized descriptor; a missing worker. "
             "The worker's table is read inside the exec'ed worker" +
             (" (setuid to a separate uid)" if lab.root_mode else " (same uid: not tamper-proof)") +
             ", the caller's from /proc before and after")
    receipt.add_evidence("TESTED", "run_worker passes exactly the authorized open file at descriptor 3, keeps "
                         "the caller's table unchanged, reaps the worker and reports its result", "pass", scope,
                         cases=len(outcomes))


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
