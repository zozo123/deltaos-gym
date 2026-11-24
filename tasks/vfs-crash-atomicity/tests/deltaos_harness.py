"""DeltaOS trusted grader harness. One file, standard library only.

scripts/vendor_harness.py copies this file byte for byte into every
tasks/*/tests/ directory, because a Harbor verifier image only receives tests/.

What every grader gets from it, and must not work around:

1. Candidate code never runs in the grader's process. When the grader is root
   (a Harbor verifier container), candidate code also runs as another user that
   can neither read tests/ nor write the verdict directory.
2. The verdict is computed here from data. Nothing a candidate prints is a verdict.
3. Hidden cases are drawn fresh for every episode from a seed that the receipt
   records, so a run can be replayed and a test set cannot be memorised.
4. Evidence is named. A receipt lists each claim with the class of evidence
   behind it; a weaker class is never reported as a stronger one.
5. Fail closed. A crash, a timeout or a missing required tool is reward 0.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import pathlib
import platform
import random
import re
import resource
import secrets
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import traceback

VERSION = "1.0.0"
RECEIPT_SCHEMA = "deltaos.receipt/1"

# Ordered weakest to strongest for the one-word summary only. The receipt's
# "evidence" list is the real statement; no class implies another.
EVIDENCE_CLASSES = ("COMPILED", "KERNEL_ACCEPTED", "TESTED", "MODEL_CHECKED", "PROVED_WITHIN_MODEL")
ASSURANCE = EVIDENCE_CLASSES + ("REFUTED", "UNKNOWN")

TESTS = pathlib.Path(os.environ.get("DELTAOS_TESTS") or pathlib.Path(__file__).resolve().parent)
WORKSPACE = pathlib.Path(os.environ.get("DELTAOS_WORKSPACE", "/workspace"))
LOGS = pathlib.Path(os.environ.get("DELTAOS_LOGS", "/logs/verifier"))

LINUX = sys.platform.startswith("linux")
_libc = ctypes.CDLL(None, use_errno=True) if LINUX else None
_PR_SET_PDEATHSIG, _PR_SET_NO_NEW_PRIVS, _CLONE_NEWNET = 1, 38, 0x40000000

MiB = 1 << 20
CANDIDATE_LIMITS = {"cpu": 20, "as": 2048 * MiB, "fsize": 64 * MiB, "nofile": 256}
TOOL_LIMITS = {"cpu": 300, "as": 16384 * MiB, "fsize": 1024 * MiB, "nofile": 1024}


class Reject(Exception):
    """The candidate is wrong. `detail` becomes the receipt's counterexample."""

    def __init__(self, reason: str, **detail):
        super().__init__(reason)
        self.detail = {"reason": reason, **detail}


class GraderError(Exception):
    """The grader could not reach a verdict (missing tool, broken environment)."""


# --------------------------------------------------------------------------- seeds

def episode_seed() -> str:
    """DELTAOS_SEED replays an episode; otherwise every episode gets fresh cases."""
    return os.environ.get("DELTAOS_SEED") or secrets.token_hex(16)


def rng(seed: str, stream: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}/{stream}".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


# --------------------------------------------------------------------------- artifacts

def read_artifact(name: str, *, max_bytes: int = 200_000) -> bytes:
    """Read one agent artifact as data. Symlinks, devices and oversized files are refused."""
    path = WORKSPACE / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise Reject("artifact_unreadable", artifact=name, error=type(exc).__name__)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Reject("artifact_not_a_regular_file", artifact=name)
        if info.st_size > max_bytes:
            raise Reject("artifact_too_large", artifact=name, bytes=info.st_size, limit=max_bytes)
        data = b""
        while len(data) <= max_bytes:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
        if len(data) > max_bytes:
            raise Reject("artifact_too_large", artifact=name, limit=max_bytes)
        return data
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- sandbox

class Result:
    __slots__ = ("returncode", "stdout", "stderr", "timed_out", "seconds")

    def __init__(self, returncode, stdout, stderr, timed_out, seconds):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.timed_out, self.seconds = timed_out, seconds

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def text(self, limit: int = 2000) -> str:
        return (self.stdout + self.stderr).decode("utf-8", "replace")[-limit:]


class Sandbox:
    """Where untrusted candidate code is built and run.

    As root: a private directory owned by an unprivileged uid, and every process
    started here runs as that uid in its own session with resource limits,
    no_new_privs, a scrubbed environment and (when the kernel allows it) no
    network. Not as root: the same minus the uid switch, reported as "same-uid".
    """

    def __init__(self):
        self.separated = LINUX and os.geteuid() == 0
        self.uid = int(os.environ.get("DELTAOS_SANDBOX_UID", "65534")) if self.separated else os.getuid()
        self.gid = int(os.environ.get("DELTAOS_SANDBOX_GID", str(self.uid))) if self.separated else os.getgid()
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="deltaos-sbx-"))
        os.chmod(self.root, 0o711)
        self.dir = self.root / "box"
        self.dir.mkdir()
        self._own(self.dir, 0o700)
        self.io = self.root / "io"          # stdin/stdout capture files, trusted side only
        self.io.mkdir(mode=0o700)
        self.network = "inherited"
        self._pgids: set[int] = set()
        self._count = 0

    # -- files
    def _own(self, path, mode):
        if self.separated:
            os.chown(path, self.uid, self.gid)
        os.chmod(path, mode)

    def path(self, name: str) -> pathlib.Path:
        return self.dir / name

    def put(self, name: str, data: bytes | str, mode: int = 0o644) -> pathlib.Path:
        """Place a file in the box (the candidate may read and, in its own box, replace it)."""
        target = self.dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent != self.dir:
            self._own(target.parent, 0o700)
        target.write_bytes(data.encode() if isinstance(data, str) else data)
        self._own(target, mode)
        return target

    # -- processes
    def _preexec(self, limits, allow_privilege_gain, isolate_network):
        separated, uid, gid = self.separated, self.uid, self.gid

        def setup():
            os.setsid()
            for key, number in (("cpu", resource.RLIMIT_CPU), ("as", resource.RLIMIT_AS),
                                ("fsize", resource.RLIMIT_FSIZE), ("nofile", resource.RLIMIT_NOFILE)):
                if key in limits:
                    try:
                        resource.setrlimit(number, (limits[key], limits[key]))
                    except (ValueError, OSError):
                        pass
            try:
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            except (ValueError, OSError):
                pass
            if separated:
                if isolate_network:
                    _libc.unshare(_CLONE_NEWNET)      # needs CAP_SYS_ADMIN; best effort
                os.setgroups([])
                os.setgid(gid)
                os.setuid(uid)
            if LINUX:
                _libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
                if not allow_privilege_gain:
                    _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        return setup

    def _env(self, extra):
        env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
               "LANG": "C", "LC_ALL": "C", "HOME": str(self.dir), "TMPDIR": str(self.dir)}
        env.update(extra or {})
        return env

    def popen(self, argv, *, cwd=None, env=None, limits=None, pass_fds=(),
              allow_privilege_gain=False, isolate_network=True, **streams) -> subprocess.Popen:
        """Start a candidate process; the caller owns its pipes. Prefer run()."""
        limits = dict(CANDIDATE_LIMITS if limits is None else limits)
        proc = subprocess.Popen(
            [str(a) for a in argv], cwd=str(cwd or self.dir), env=self._env(env),
            pass_fds=pass_fds, close_fds=True,
            preexec_fn=self._preexec(limits, allow_privilege_gain, isolate_network), **streams)
        self._pgids.add(proc.pid)
        return proc

    def run(self, argv, *, input: bytes = b"", timeout: float = 30.0, cwd=None, env=None,
            limits=None, max_output: int = 16 * MiB, pass_fds=(),
            allow_privilege_gain=False, isolate_network=True) -> Result:
        """Run to completion. Output beyond max_output kills the process (RLIMIT_FSIZE)."""
        limits = dict(CANDIDATE_LIMITS if limits is None else limits)
        limits["fsize"] = max(limits.get("fsize", 0), max_output)
        self._count += 1
        stem = self.io / f"run{self._count}"
        files = {}
        for suffix in ("in", "out", "err"):
            files[suffix] = pathlib.Path(f"{stem}.{suffix}")
        files["in"].write_bytes(input)
        started = time.monotonic()
        timed_out = False
        with open(files["in"], "rb") as fin, open(files["out"], "wb") as fout, open(files["err"], "wb") as ferr:
            proc = self.popen(argv, cwd=cwd, env=env, limits=limits, pass_fds=pass_fds,
                              allow_privilege_gain=allow_privilege_gain,
                              isolate_network=isolate_network, stdin=fin, stdout=fout, stderr=ferr)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            self._kill_group(proc.pid)
            proc.wait()
        out = files["out"].read_bytes()[:max_output]
        err = files["err"].read_bytes()[:max_output]
        for item in files.values():
            item.unlink(missing_ok=True)
        return Result(proc.returncode, out, err, timed_out, time.monotonic() - started)

    def _kill_group(self, pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def kill_all(self):
        """Nothing a candidate started survives the grader, even after setsid()."""
        for pgid in list(self._pgids):
            self._kill_group(pgid)
        if self.separated:
            pid = os.fork()
            if pid == 0:
                try:
                    os.setgroups([])
                    os.setgid(self.gid)
                    os.setuid(self.uid)
                    os.kill(-1, signal.SIGKILL)   # every process of the sandbox uid
                finally:
                    os._exit(0)
            os.waitpid(pid, 0)

    def close(self):
        self.kill_all()
        shutil.rmtree(self.root, ignore_errors=True)

    def describe(self) -> dict:
        return {"mode": "uid-separated" if self.separated else "same-uid",
                "uid": self.uid, "no_new_privs": LINUX, "own_session": True,
                "limits": {k: v for k, v in CANDIDATE_LIMITS.items()}}


def lock_down() -> bool:
    """As root, make tests/ and the verdict directory unreadable for the sandbox uid."""
    if not (LINUX and os.geteuid() == 0):
        return False
    locked = True
    for path in (TESTS, LOGS):
        try:
            os.chown(path, 0, 0)
            os.chmod(path, 0o700)
        except OSError:
            locked = False
    return locked


# --------------------------------------------------------------------------- tools

def tool_version(name: str, flag: str = "--version") -> str | None:
    exe = shutil.which(name)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, flag], capture_output=True, text=True, timeout=20)
        lines = (out.stdout or out.stderr).strip().splitlines()
        return lines[0].strip() if lines else ""
    except (OSError, subprocess.SubprocessError):
        return None


def degraded_allowed() -> bool:
    return os.environ.get("DELTAOS_ALLOW_DEGRADED") == "1"


def multiarch_include() -> str | None:
    """/usr/include/<triplet>, needed for <asm/types.h> when compiling for the BPF target."""
    try:
        triplet = subprocess.run(["gcc", "-print-multiarch"], capture_output=True, text=True,
                                 timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        triplet = ""
    for candidate in ([f"/usr/include/{triplet}"] if triplet else []) + \
            [f"/usr/include/{platform.machine()}-linux-gnu"]:
        if os.path.isdir(candidate):
            return candidate
    return None


def bpf_cflags() -> list[str]:
    flags = ["-target", "bpf", "-O2", "-g", "-mcpu=v3", "-ffreestanding", "-fno-stack-protector",
             "-Wall", "-Wno-unused-parameter"]
    include = multiarch_include()
    if include:
        flags.append("-I" + include)
    return flags


def object_report(sbx: Sandbox, obj: str) -> dict:
    """Symbols and sections of a candidate object, for freestanding/purity checks."""
    undefined = sbx.run(["nm", "--undefined-only", "--format=posix", obj], limits=TOOL_LIMITS)
    sections = sbx.run(["size", "-A", obj], limits=TOOL_LIMITS)
    if not undefined.ok or not sections.ok:
        raise GraderError("binutils failed: " + undefined.text(300) + sections.text(300))
    sizes = {}
    for line in sections.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(".") and parts[1].isdigit():
            sizes[parts[0]] = int(parts[1])
    return {"undefined": sorted(l.split()[0] for l in undefined.stdout.decode().splitlines() if l.strip()),
            "sections": sizes}


def require_freestanding(report: dict, *, allowed_undefined=(), allow_mutable_state=False):
    """A pure decision function needs no library, no start-up code and no memory between calls."""
    extra = [s for s in report["undefined"] if s not in allowed_undefined]
    if extra:
        raise Reject("candidate_calls_outside_itself", undefined_symbols=extra[:20])
    startup = [s for s in report["sections"]
               if s.startswith((".init_array", ".fini_array", ".ctors", ".dtors", ".preinit_array"))]
    if startup:
        raise Reject("candidate_runs_code_at_load_time", sections=startup)
    if not allow_mutable_state:
        state = {s: n for s, n in report["sections"].items()
                 if n and (s.startswith((".data", ".bss", ".tdata", ".tbss")))}
        if state:
            raise Reject("candidate_keeps_state_between_calls", sections=state)


# --------------------------------------------------------------------------- plain integer C

# A decision function that is tested and proved natively but shipped as BPF must not
# be able to tell the two apart. x86-64 and BPF agree on every integer type (char is
# signed, int 32-bit, long and pointers 64-bit, little-endian) and disagree on
# long double (16 vs 8 bytes). So the rule is: integer arithmetic on the arguments,
# nothing that asks the compiler or the machine about itself, and no addresses.
_C_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<string>[LuU8]*"(?:\\.|[^"\\\n])*")
  | (?P<char>[LuU]?'(?:\\.|[^'\\\n])+')
  | (?P<number>\.?\d(?:[eEpP][+-]|[\w.])*)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<punct>\.\.\.|<<=|>>=|->|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&|^]=|[][(){};,?:~!<>=+\-*/%&|^.#])
""", re.X)
_BANNED_WORDS = {
    "sizeof", "_Alignof", "alignof", "__alignof", "__alignof__", "_Alignas", "alignas", "_Generic",
    "asm", "__asm", "__asm__", "float", "double", "_Float16", "_Float32", "_Float64", "_Float128",
    "_Complex", "__complex__", "_Imaginary", "volatile", "__volatile", "__volatile__",
    "__attribute", "__attribute__", "__declspec", "typeof", "__typeof", "__typeof__", "typeof_unqual",
    "__auto_type", "__int128", "__int128_t", "__uint128_t", "_BitInt", "union", "_Atomic",
    "_Thread_local", "thread_local", "__thread", "extern", "__extension__", "__label__", "goto",
}
_BANNED_PREFIXES = ("__builtin", "__sync", "__atomic", "__c11", "__CPROVER", "__opencl")
_KEYWORDS = {
    "auto", "break", "case", "const", "continue", "default", "do", "else", "enum", "for", "if", "inline",
    "__inline", "__inline__", "int", "long", "register", "restrict", "__restrict", "__restrict__", "return",
    "char", "short", "signed", "__signed", "__signed__", "static", "struct", "switch", "typedef", "unsigned", "void",
    "while", "_Bool", "bool", "_Static_assert", "static_assert", "_Noreturn", "true", "false",
} | _BANNED_WORDS
_TYPE_WORDS = {"char", "unsigned", "signed", "__signed", "__signed__", "int", "long", "short", "_Bool", "bool", "const",
               "void", "struct", "enum", "restrict", "__restrict", "__restrict__", "*"}


def integer_c_problems(text: str, *, function: str | None = None, structs=()) -> list[str]:
    """Why `text` (a preprocessed translation unit) is not plain integer C. Empty if it is.

    Pointer parameters of `function` may only be used as `p->field` (or tested with `!p`).
    `structs` names the struct tags the task's ABI uses; no other struct is allowed.
    """
    tokens, pos = [], 0
    while pos < len(text):
        match = _C_TOKEN.match(text, pos)
        if not match:
            return [f"unexpected character {text[pos]!r}"]
        pos = match.end()
        if match.lastgroup != "ws":
            tokens.append((match.lastgroup, match.group()))
    problems: list[str] = []

    def bad(message):
        if message not in problems:
            problems.append(message)

    typedefs, depth, inside = set(), 0, False
    for kind, value in tokens:
        if value == "typedef" and depth == 0:
            inside = True
        elif inside and value == ";" and depth == 0:
            inside = False
        elif value in "({":
            depth += 1
        elif value in ")}":
            depth -= 1
        elif inside and kind == "name" and value not in _KEYWORDS:
            typedefs.add(value)
    functions = {v for i, (k, v) in enumerate(tokens[:-1])
                 if k == "name" and tokens[i + 1][1] == "(" and v not in _KEYWORDS and v not in typedefs}
    pointer_params: set[str] = set()
    if function:
        for i, (kind, value) in enumerate(tokens[:-1]):
            if value != function or tokens[i + 1][1] != "(":
                continue
            j, level, params, current = i + 2, 1, [], []
            while j < len(tokens) and level:
                v = tokens[j][1]
                level += v == "("
                level -= v == ")"
                if level == 0 or (v == "," and level == 1):
                    params.append(current)
                    current = []
                else:
                    current.append(tokens[j])
                j += 1
            if j < len(tokens) and tokens[j][1] == "{":
                for param in params:
                    names = [v for k, v in param if k == "name" and v not in _KEYWORDS]
                    if any(v == "*" for _, v in param) and names:
                        pointer_params.add(names[-1])

    def is_cast(close_index):
        level, j = 0, close_index
        while j >= 0:
            level += tokens[j][1] == ")"
            level -= tokens[j][1] == "("
            if level == 0:
                break
            j -= 1
        inner = tokens[j + 1:close_index]
        return bool(inner) and all(
            v in _TYPE_WORDS or v in typedefs or (k == "name" and n > 0 and inner[n - 1][1] in ("struct", "enum"))
            for n, (k, v) in enumerate(inner))

    def unary(i):
        if i == 0:
            return True
        kind, value = tokens[i - 1]
        if kind in ("number", "char"):
            return False
        if kind == "name":
            return value in _KEYWORDS
        if value == "]":
            return False
        if value == ")":
            return is_cast(i - 1)
        return True

    for i, (kind, value) in enumerate(tokens):
        nxt = tokens[i + 1][1] if i + 1 < len(tokens) else None
        prev = tokens[i - 1][1] if i else None
        if kind == "string":
            bad("string literals")
        elif kind == "number":
            hexa = value.lower().startswith("0x")
            if "." in value or (hexa and "p" in value.lower()) or (not hexa and "e" in value.lower()):
                bad("floating-point constants")
        elif kind == "name":
            if value in _BANNED_WORDS or value.startswith(_BANNED_PREFIXES):
                bad(f"`{value}`")
            elif value == "struct" and nxt not in structs:
                bad("struct types other than " + (", ".join(f"`struct {s}`" for s in structs) or "none"))
            elif value in functions and nxt != "(":
                bad(f"the function name `{value}` used as a value")
            elif value in pointer_params and nxt != "->" and prev != "!" and not (prev == "*" and nxt in (",", ")")):
                bad(f"the pointer `{value}` used other than as `{value}->field`")
        elif value in ("[", "]"):
            bad("arrays and subscripts")
        elif value == "#":
            bad("pragmas or other directives")
        elif value in (".", "..."):
            bad("`.` member access or variadic functions")
        elif value in ("&", "&&") and unary(i):
            bad("taking an address (`&`)")
    return problems


def require_integer_c(text: str, **rules):
    problems = integer_c_problems(text, **rules)
    if problems:
        raise Reject("not_plain_integer_c", uses=problems[:12])


# --------------------------------------------------------------------------- CBMC

CBMC_CHECKS = ["--bounds-check", "--pointer-check", "--div-by-zero-check", "--signed-overflow-check",
               "--undefined-shift-check", "--pointer-overflow-check"]


def cbmc(sbx: Sandbox, files, *, entry: str, track=(), unwind: int | None = 16,
         timeout: float = 180.0, extra=()) -> dict:
    """Bounded model checking of `entry`. Returns {"status": proved|refuted|error, ...}.

    "proved" means every assertion and every undefined-behaviour check in
    CBMC_CHECKS holds for all inputs, within CBMC's C semantics and, when the
    code has loops, with every loop shown to finish within `unwind` iterations.
    """
    if not shutil.which("cbmc"):
        return {"status": "error", "reason": "cbmc not installed"}
    argv = ["cbmc", *files, "--function", entry, "--json-ui", "--trace", *CBMC_CHECKS, *extra]
    if unwind is not None:
        argv += ["--unwind", str(unwind), "--unwinding-assertions"]
    result = sbx.run(argv, timeout=timeout, limits=TOOL_LIMITS, max_output=64 * MiB)
    if result.timed_out:
        return {"status": "error", "reason": "cbmc timed out", "seconds": round(result.seconds, 2)}
    try:
        messages = json.loads(result.stdout.decode("utf-8", "replace"))
    except ValueError:
        return {"status": "error", "reason": "cbmc output unreadable", "log": result.text(800)}
    properties, failures = [], []
    for message in messages:
        if isinstance(message, dict) and "result" in message:
            properties = message["result"]
    if not properties:
        errors = [m.get("messageText", "") for m in messages
                  if isinstance(m, dict) and m.get("messageType") == "ERROR"]
        return {"status": "error", "reason": "cbmc produced no result", "log": " | ".join(errors)[-800:]}
    for prop in properties:
        if prop.get("status") != "SUCCESS":
            failures.append(prop)
    out = {"properties": len(properties), "seconds": round(result.seconds, 2)}
    if not failures:
        return {"status": "proved", **out}
    first = failures[0]
    witness = {}
    for step in first.get("trace", []):
        if step.get("stepType") == "assignment" and step.get("lhs") in track:
            value = step.get("value", {})
            data = value.get("data")
            try:
                witness[step["lhs"]] = int(str(data).rstrip("uUlL"))
            except (TypeError, ValueError):
                witness[step["lhs"]] = data
    return {"status": "refuted", **out, "failed_properties": len(failures),
            "property": first.get("description", first.get("property", "")),
            "witness": witness}


# --------------------------------------------------------------------------- kernel tier

def kernel_tier() -> str:
    """off (default) | auto | required. Loading candidate BPF needs a disposable privileged VM."""
    mode = os.environ.get("DELTAOS_KERNEL_TIER", "off")
    return mode if mode in ("off", "auto", "required") else "off"


def bpf_capable() -> tuple[bool, str]:
    """Can this process load a BPF program? Tries the smallest possible one."""
    if not LINUX:
        return False, "not Linux"
    if os.geteuid() != 0:
        return False, "not root"
    number = {"x86_64": 321, "aarch64": 280, "riscv64": 280}.get(platform.machine())
    if number is None:
        return False, "unknown syscall number for " + platform.machine()
    insns = struct.pack("<BBhi", 0xb7, 0, 0, 0) + struct.pack("<BBhi", 0x95, 0, 0, 0)  # r0 = 0; exit
    insn_buf = ctypes.create_string_buffer(insns, len(insns))
    license_buf = ctypes.create_string_buffer(b"GPL")
    attr = ctypes.create_string_buffer(128)
    struct.pack_into("<IIQQ", attr, 0, 1, 2, ctypes.addressof(insn_buf), ctypes.addressof(license_buf))
    fd = _libc.syscall(number, 5, attr, 128)       # BPF_PROG_LOAD, BPF_PROG_TYPE_SOCKET_FILTER
    if fd < 0:
        return False, "bpf(BPF_PROG_LOAD) refused: " + os.strerror(ctypes.get_errno())
    os.close(fd)
    return True, "ok"


def kernel_tier_decision() -> tuple[bool, str]:
    """(run it?, why not). Raises GraderError when required but impossible."""
    mode = kernel_tier()
    if mode == "off":
        return False, "NOT_RUN: kernel tier is off (set DELTAOS_KERNEL_TIER=auto in a disposable privileged VM)"
    capable, why = bpf_capable()
    if capable:
        return True, ""
    if mode == "required":
        raise GraderError("kernel tier required but unavailable: " + why)
    return False, "NOT_RUN: " + why


# --------------------------------------------------------------------------- receipt

def grader_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in TESTS.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(TESTS).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


class Receipt:
    """The claim-scoped record of one grading run. Written even when grading fails."""

    def __init__(self, task_id: str, model: str, seed: str):
        self._started = time.monotonic()
        self.checks: dict[str, object] = {}
        self.evidence: list[dict] = []
        self.artifacts: list[dict] = []
        self.counterexample: dict | None = None
        self.error: str | None = None
        self.degraded = False
        self.extra: dict[str, object] = {}
        self.isolation: dict = {}
        self.task_id, self.model, self.seed = task_id, model, seed
        self.episode_id = os.environ.get("DELTAOS_EPISODE_ID") or secrets.token_hex(8)
        self.kernel_profile: str | None = None

    def artifact(self, name: str, data: bytes):
        self.artifacts.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})

    def check(self, name: str, value):
        """True, False, or a string starting with NOT_RUN for an optional tier that did not run."""
        self.checks[name] = value

    def add_evidence(self, cls: str, claim: str, status: str, scope: str = "", **detail):
        assert cls in EVIDENCE_CLASSES and status in ("pass", "fail", "not_run")
        item = {"class": cls, "claim": claim, "status": status, "scope": scope}
        if detail:
            item["detail"] = detail
        self.evidence.append(item)

    def _assurance(self, passed: bool) -> str:
        if self.error is not None:
            return "UNKNOWN"
        if not passed:
            return "REFUTED"
        held = [e["class"] for e in self.evidence if e["status"] == "pass"]
        return max(held, key=EVIDENCE_CLASSES.index) if held else "UNKNOWN"

    def document(self, passed: bool) -> dict:
        manifest = hashlib.sha256()
        for item in self.artifacts:
            manifest.update(f"{item['sha256']}  {item['path']}\n".encode())
        single = self.artifacts[0]["sha256"] if len(self.artifacts) == 1 else manifest.hexdigest()
        return {
            "schema": RECEIPT_SCHEMA,
            "task_id": self.task_id,
            "episode_id": self.episode_id,
            "reward": 1 if passed else 0,
            "passed": passed,
            "assurance": self._assurance(passed),
            "evidence": self.evidence,
            "checks": self.checks,
            "artifact_sha256": single,
            "artifacts": self.artifacts,
            "seed": self.seed,
            "grader": {"harness": VERSION, "model": self.model, "sha256": grader_digest()},
            "isolation": self.isolation,
            "environment": {
                "kernel_release": platform.release(), "machine": platform.machine(),
                "python": platform.python_version(),
                "gcc": tool_version("gcc"), "clang": tool_version("clang"), "cbmc": tool_version("cbmc"),
            },
            "degraded": self.degraded,
            "counterexample": self.counterexample,
            "error": self.error,
            "kernel_profile": self.kernel_profile,
            "runtime_ms": int((time.monotonic() - self._started) * 1000),
            "trace_uri": None,
            **self.extra,
        }


def _write_atomic(path: pathlib.Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class Context:
    def __init__(self, task_id: str, model: str):
        self.seed = episode_seed()
        self.receipt = Receipt(task_id, model, self.seed)
        self.sandbox = Sandbox()
        self.receipt.isolation = self.sandbox.describe()

    def rng(self, stream: str) -> random.Random:
        return rng(self.seed, stream)

    def require_tool(self, name: str, check: str) -> bool:
        """A tool an evidence tier needs. Missing means reward 0 unless DELTAOS_ALLOW_DEGRADED=1."""
        if shutil.which(name):
            return True
        if not degraded_allowed():
            raise GraderError(f"required tool missing: {name} (needed for {check})")
        self.receipt.degraded = True
        self.receipt.check(check, f"NOT_RUN: {name} not installed (degraded run)")
        return False


def run_grader(task_id: str, model: str, body) -> int:
    """Run `body(ctx)` and always leave reward.txt, receipt.json and feedback.json behind.

    The body registers checks and evidence and raises Reject for a wrong candidate.
    The run passes only if at least one check is True and none is False.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    _write_atomic(LOGS / "reward.txt", "0\n")       # fail closed before anything else can happen
    ctx = Context(task_id, model)
    ctx.receipt.isolation["trusted_dirs_locked"] = lock_down()
    receipt = ctx.receipt
    try:
        try:
            body(ctx)
        finally:
            ctx.sandbox.close()
        values = list(receipt.checks.values())
        passed = any(v is True for v in values) and not any(v is False for v in values)
        if not passed and receipt.counterexample is None:
            receipt.counterexample = {"reason": "check_failed",
                                      "failed": [k for k, v in receipt.checks.items() if v is False]}
    except Reject as rejection:
        passed = False
        receipt.counterexample = rejection.detail
    except Exception as exc:                          # includes GraderError: no verdict
        passed = False
        where = traceback.extract_tb(exc.__traceback__)[-1]
        receipt.error = f"{type(exc).__name__}: {exc} (at {pathlib.Path(where.filename).name}:{where.lineno})"[:2000]
    document = receipt.document(passed)
    text = json.dumps(document, indent=2, default=str) + "\n"
    _write_atomic(LOGS / "receipt.json", text)
    _write_atomic(LOGS / "feedback.json", text)
    _write_atomic(LOGS / "reward.txt", "1\n" if passed else "0\n")
    summary = {k: document[k] for k in ("task_id", "reward", "assurance", "seed", "runtime_ms")}
    summary["checks"] = document["checks"]
    if document["counterexample"]:
        summary["counterexample"] = document["counterexample"]
    if document["error"]:
        summary["error"] = document["error"]
    print(json.dumps(summary, indent=2, default=str))
    return 0
