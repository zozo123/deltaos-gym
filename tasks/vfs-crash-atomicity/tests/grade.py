#!/usr/bin/env python3
"""Grader for vfs-crash-atomicity: model checking publish() against restricted-vfs-crash-v2.

The candidate is linked into a trusted fork server (shim.c) that forwards each vfs_api
call to this process. The persistence model lives only here; nothing the candidate's
process says is a verdict. For payloads of 0-3 bytes every schedule is explored: every
short write, up to two interrupted writes and up to two I/O errors anywhere. Larger
payloads get sampled schedules. At every point between two calls the grader asks what
a crash would leave on disk.
"""
import errno
import os
import pathlib
import re
import select
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/vfs-crash-atomicity"
MODEL = "restricted-vfs-crash-v2"
EIO, EINTR, EBADF, ENOENT, EEXIST = (-errno.EIO, -errno.EINTR, -errno.EBADF, -errno.ENOENT, -errno.EEXIST)
MAX_EIO, MAX_EINTR = 2, 2
MAX_SENT = 65536
MAX_SCHEDULES = 60000
TORN = "torn"
NAMES = {b"C": "create_temp", b"W": "write_temp", b"F": "fsync_temp", b"X": "close_temp",
         b"N": "rename_temp", b"D": "fsync_directory", b"U": "remove_temp"}


class Violation(Exception):
    def __init__(self, reason, **detail):
        super().__init__(reason)
        self.detail = {"reason": reason, **detail}


class Nondeterministic(Exception):
    pass


class Inode:
    """`intact`: a successful fsync came after creation and after the last write."""

    def __init__(self):
        self.data = bytearray()
        self.intact = False
        self.poisoned = False

    def after_crash(self):
        return bytes(self.data) if self.intact and not self.poisoned else TORN


class Chooser:
    """Decides each call's outcome: from a prefix of indices (exploration), from recorded
    values (replay), or from a random policy (sampling). Records what it decided.
    `options` lists the discrete outcomes; with `upto`, any write size 1..upto is legal too."""

    def __init__(self, prefix=(), replay=None, policy=None):
        self.prefix, self.replay, self.policy = list(prefix), replay, policy
        self.taken, self.widths, self.values = [], [], []

    def decide(self, kind, options, upto=0):
        i = len(self.values)
        legal = lambda v: v in options or 0 < v <= upto
        if self.replay is not None:
            if i >= len(self.replay) or not legal(self.replay[i]):
                raise Nondeterministic()
            value = self.replay[i]
        elif i < len(self.prefix):
            if self.prefix[i] >= len(options):
                raise Nondeterministic()
            value = options[self.prefix[i]]
        elif self.policy is not None:
            value = self.policy(kind, options, upto)
        else:
            value = options[0]
        self.taken.append(options.index(value) if value in options else 0)
        self.widths.append(len(options))
        self.values.append(value)
        return value


class Model:
    def __init__(self, old, new, chooser, exhaustive):
        self.old, self.new, self.chooser, self.exhaustive = old, new, chooser, exhaustive
        self.temp = None          # inode under the temporary name
        self.fd = None            # inode behind the open descriptor
        self.durable = None       # inode whose rename is durable (None: the old file)
        self.pending = []         # inodes renamed since the last durable directory fsync
        self.dir_poisoned = False
        self.eio = self.eintr = 0
        self.trace = []
        self.crash_points = 0

    def _fault(self, options):
        if self.eio < MAX_EIO:
            options.append(EIO)
        return options

    def _decide(self, kind, options, upto=0):
        value = self.chooser.decide(kind, options, upto)
        self.eio += value == EIO
        self.eintr += value == EINTR
        return value

    def content(self, inode):
        return self.old if inode is None else inode.after_crash()

    def crash_states(self):
        return [self.content(self.durable)] + [self.content(inode) for inode in self.pending]

    def boundary(self):
        self.crash_points += 1
        for state in self.crash_states():
            if state is TORN or state not in (self.old, self.new):
                raise Violation("a_crash_here_leaves_a_torn_or_wrong_file", after=self.trace[-16:],
                                on_disk=self.describe(state))

    def describe(self, state):
        if state is TORN:
            return "torn (an inode that was not fsynced after its last write, or whose fsync failed)"
        return "old content" if state == self.old else ("new content" if state == self.new else
                                                         "wrong bytes: " + state[:24].hex())

    def call(self, tag, data=b"", offered=0):
        if tag == b"C":
            answer = EEXIST if self.temp is not None else self._decide("create", self._fault([0]))
            if answer == 0:
                self.temp = self.fd = Inode()
        elif tag == b"W":
            if self.fd is None:
                answer = EBADF
            elif offered == 0:
                answer = 0
            else:
                upto = 0
                if not self.exhaustive:
                    options, upto = [offered], offered
                elif offered <= 4:
                    options = [offered] + list(range(1, offered))
                else:
                    options = sorted({offered, 1, offered // 2, offered - 1}, reverse=True)
                if self.eintr < MAX_EINTR:
                    options.append(EINTR)
                answer = self._decide("write", self._fault(options), upto)
                if answer > 0:
                    self.fd.data += data[:answer]
                    self.fd.intact = False
        elif tag == b"F":
            inode = self.fd
            answer = EBADF if inode is None else self._decide("fsync", self._fault([0]))
            if inode is not None and answer == 0 and not inode.poisoned:
                inode.intact = True
            elif inode is not None and answer == EIO:
                inode.poisoned, inode.intact = True, False
        elif tag == b"X":
            answer = EBADF if self.fd is None else self._decide("close", self._fault([0]))
            self.fd = None
        elif tag == b"N":
            answer = ENOENT if self.temp is None else self._decide("rename", self._fault([0]))
            if answer == 0:
                self.pending.append(self.temp)
                self.temp = None
        elif tag == b"D":
            answer = self._decide("fsync_dir", self._fault([0]))
            if answer == 0 and not self.dir_poisoned and self.pending:
                self.durable, self.pending = self.pending[-1], []
            elif answer == EIO:
                self.dir_poisoned = True
        elif tag == b"U":
            answer = ENOENT if self.temp is None else self._decide("remove", self._fault([0]))
            if answer == 0:
                self.temp = None
        else:
            raise Violation("protocol_error", line=tag.decode("latin-1"))
        self.trace.append(NAMES[tag] + (f"({offered})" if tag == b"W" else "") + " -> " + _errname(answer))
        return answer

    def finish(self, rc):
        if rc == 0:
            if self.pending or self.durable is None or self.dir_poisoned:
                raise Violation("success_returned_before_the_rename_was_durable", after=self.trace[-16:])
            if self.content(self.durable) != self.new:
                raise Violation("success_returned_but_the_published_file_is_not_the_new_content",
                                after=self.trace[-16:], on_disk=self.describe(self.content(self.durable)))
        elif self.eio == 0:
            raise Violation("failure_returned_although_no_io_error_happened", returned=rc, after=self.trace[-16:])


def _errname(value):
    if value >= 0:
        return str(value)
    return "-" + (errno.errorcode.get(-value, str(-value)))


class Shim:
    def __init__(self, sbx, path):
        import subprocess as sp
        self.proc = sbx.popen([str(path)], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.DEVNULL,
                              limits={"cpu": 600, "as": 2048 * H.MiB, "fsize": 64 * H.MiB, "nofile": 64})
        self.out = self.proc.stdout.fileno()
        self.buffer = b""

    def _fill(self, deadline):
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([self.out], [], [], left)[0]:
            raise Violation("publish_did_not_finish_in_time")
        chunk = os.read(self.out, 1 << 16)
        if not chunk:
            raise Violation("the_candidate_process_died")
        self.buffer += chunk

    def line(self, deadline):
        while b"\n" not in self.buffer:
            self._fill(deadline)
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line

    def exact(self, n, deadline):
        while len(self.buffer) < n:
            self._fill(deadline)
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def send(self, data):
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except OSError:
            raise Violation("the_candidate_process_died")

    def close(self):
        try:
            self.proc.kill()
        except OSError:
            pass
        self.proc.wait()


def run_once(shim, old, new, chooser, exhaustive):
    model = Model(old, new, chooser, exhaustive)
    deadline = time.monotonic() + 20
    limit = 4 * len(new) + 64
    shim.send(b"R %d\n" % len(new) + new)
    model.boundary()
    while True:
        line = shim.line(deadline)
        tag = line[:1]
        if tag == b"E":
            rc = int(line[2:])
            status = shim.line(deadline)
            if status != b"P 0":
                raise Violation("publish_crashed_after_returning", status=status.decode("latin-1"))
            model.finish(rc)
            return model
        if tag == b"P":
            raise Violation("publish_crashed", wait_status=line[2:].decode("latin-1"), after=model.trace[-16:])
        if len(model.trace) >= limit:
            raise Violation("too_many_calls", limit=limit, after=model.trace[-16:])
        offered, data = 0, b""
        if tag == b"W":
            offered = int(line[2:])
            data = shim.exact(min(offered, MAX_SENT), deadline)
            if offered > MAX_SENT:
                raise Violation("write_larger_than_any_payload", offered=offered)
        answer = model.call(tag, data, offered)
        shim.send(b"%d\n" % answer)
        model.boundary()


def explore(shim, old, new):
    """Every schedule, by re-execution: each run takes the first option at every new decision."""
    stack, schedules, crash_points, recorded = [[]], 0, 0, []
    while stack:
        prefix = stack.pop()
        chooser = Chooser(prefix=prefix)
        try:
            model = run_once(shim, old, new, chooser, exhaustive=True)
        except Nondeterministic:
            raise Violation("publish_is_not_deterministic", schedule=prefix)
        except Violation as violation:
            violation.detail.setdefault("payload_bytes", len(new))
            raise
        schedules += 1
        crash_points += model.crash_points
        if schedules % 97 == 1:
            recorded.append(chooser.values)
        if schedules > MAX_SCHEDULES:
            raise Violation("too_many_schedules_to_explore", limit=MAX_SCHEDULES)
        for depth in range(len(prefix), len(chooser.widths)):
            for alternative in range(1, chooser.widths[depth]):
                stack.append(chooser.taken[:depth] + [alternative])
    return schedules, crash_points, recorded


def sampling_policy(rng, length):
    biggest = rng.choice([1, 3, 7, 97, 512, 4096] if length < 4096 else [7, 97, 512, 4096])
    p_eintr = rng.choice([0, 0.05, 0.25])
    p_eio = rng.choice([0, 0, 0.02, 0.1])

    def policy(kind, options, upto):
        if EIO in options and rng.random() < p_eio:
            return EIO
        if kind != "write":
            return options[0]
        if EINTR in options and rng.random() < p_eintr:
            return EINTR
        return min(upto, rng.randint(1, biggest))
    return policy


def own_lines(preprocessed, name):
    keep, out = False, []
    for line in preprocessed.splitlines():
        marker = re.match(r'#\s*\d+\s+"([^"]*)"', line)
        if marker:
            keep = os.path.basename(marker.group(1)) == name
        elif keep:
            out.append(line)
    return "\n".join(out)


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    source = H.read_artifact("publisher.c")
    receipt.artifact("publisher.c", source)
    sbx.put("publisher.c", source)
    for name in ("vfs_api.h", "shim.c"):
        sbx.put(name, (H.TESTS / name).read_bytes())
    ctx.require_tool("gcc", "crash_model")

    pre = sbx.run(["gcc", "-std=c11", "-E", "-I.", "publisher.c"], limits=H.TOOL_LIMITS, timeout=60)
    if not pre.ok:
        receipt.check("compiles", False)
        raise H.Reject("does_not_preprocess", log=pre.text(1200))
    if re.search(r"\b(asm|__asm|__asm__)\b", own_lines(pre.stdout.decode("utf-8", "replace"), "publisher.c")):
        receipt.check("compiles", False)
        raise H.Reject("inline_assembly", detail="publish() may act only through the vfs_api calls")
    build = sbx.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-fno-stack-protector", "-I.", "-c",
                     "publisher.c", "-o", "candidate.o"], limits=H.TOOL_LIMITS, timeout=60)
    receipt.check("compiles", build.ok)
    if not build.ok:
        raise H.Reject("does_not_compile", log=build.text(1200))
    try:
        H.require_freestanding(H.object_report(sbx, "candidate.o"), allow_mutable_state=True,
                               allowed_undefined=("memcpy", "memmove", "memset", "memcmp", "_GLOBAL_OFFSET_TABLE_"))
        receipt.check("only_through_vfs_api", True)
    except H.Reject:
        receipt.check("only_through_vfs_api", False)
        raise
    link = sbx.run(["gcc", "-std=c11", "-O2", "-I.", "shim.c", "candidate.o", "-o", "shim"],
                   limits=H.TOOL_LIMITS, timeout=60)
    if not link.ok:
        raise H.Reject("does_not_link", log=link.text(1200))

    rng = ctx.rng("payloads")
    shim = Shim(sbx, sbx.path("shim"))
    try:
        total_schedules = total_points = 0
        recorded = []
        for length in range(0, 4):
            old = bytes(rng.randrange(256) for _ in range(5))
            new = bytes(rng.randrange(256) for _ in range(length))
            if new == old:
                new = bytes([(new[0] + 1) % 256]) + new[1:] if new else new
            schedules, points, samples = explore(shim, old, new)
            total_schedules += schedules
            total_points += points
            recorded += [(old, new, values) for values in samples]
        receipt.check("crash_model_exhaustive", True)
        receipt.extra["schedules_explored"] = total_schedules
        receipt.add_evidence(
            "MODEL_CHECKED", "every crash point of every schedule leaves the old or the new content, success means "
            "durable, and failure only follows an I/O error", "pass",
            f"{total_schedules:,} schedules ({total_points:,} crash points) for payloads of 0-3 bytes: every "
            f"short write, up to {MAX_EINTR} interrupted writes and up to {MAX_EIO} I/O errors at any call; "
            f"model {MODEL} (Linux fsync and rename semantics, documented in vfs_api.h), not a real file system",
            schedules=total_schedules, crash_points=total_points)

        sampled = sampled_points = 0
        for length in (39, 1001, 4096):
            for _ in range(60):
                old = bytes(rng.randrange(256) for _ in range(rng.randint(1, 64)))
                new = bytes(rng.randrange(256) for _ in range(length))
                chooser = Chooser(policy=sampling_policy(rng, length))
                try:
                    model = run_once(shim, old, new, chooser, exhaustive=False)
                except Violation as violation:
                    violation.detail.setdefault("payload_bytes", length)
                    raise
                sampled += 1
                sampled_points += model.crash_points
                if sampled % 20 == 0:
                    recorded.append((old, new, chooser.values))
        receipt.check("crash_model_sampled", True)
        receipt.add_evidence("TESTED", "the same holds for larger payloads", "pass",
                             f"{sampled} sampled schedules ({sampled_points:,} crash points) for 39, 1001 and "
                             "4096-byte payloads with random chunk sizes, interrupted writes and I/O errors",
                             schedules=sampled)

        for old, new, values in recorded:                 # same schedule, same calls?
            first = run_once(shim, old, new, Chooser(replay=values), exhaustive=False)
            second = run_once(shim, old, new, Chooser(replay=values), exhaustive=False)
            if first.trace != second.trace:
                raise Violation("publish_is_not_deterministic", first=first.trace[-8:], second=second.trace[-8:])
        receipt.check("deterministic", True)
    except Nondeterministic:
        receipt.check("deterministic", False)
        raise H.Reject("publish_is_not_deterministic")
    except Violation as violation:
        receipt.check("crash_model_exhaustive" if "crash_model_exhaustive" not in receipt.checks
                      else "crash_model_sampled", False)
        raise H.Reject(**violation.detail)
    finally:
        shim.close()


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
