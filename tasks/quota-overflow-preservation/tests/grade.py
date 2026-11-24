#!/usr/bin/env python3
"""Grader for quota-overflow-preservation.

Evidence, in the order it is collected:
  COMPILED             charge() compiles into the XDP program and the case runner
  PROVED_WITHIN_MODEL  CBMC: for all 2^192 states and amounts the result follows the contract
  TESTED               the same text, built natively, gives the contract's state on every case
  KERNEL_ACCEPTED      (kernel tier) the running kernel's verifier loads the object
  TESTED in kernel     (kernel tier) the bytecode on every case; the XDP path on a real map

The candidate is preprocessed once for the BPF target and must be plain integer C, with
the state pointer used only as `state->field`. Candidate code runs last.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/quota-overflow-preservation"
MODEL = "c-state-transition/2"
MAX = (1 << 64) - 1
VALUES = [0, 1, 2, 3, 7, 1024, (1 << 32) - 1, 1 << 32, (1 << 32) + 1, (1 << 63) - 1, 1 << 63, MAX - 1, MAX]
XDP_CASES = 512


def contract(remaining, total, amount):
    if amount > remaining or amount > MAX - total:
        return (0, remaining, total)
    return (1, remaining - amount, total + amount)


def build_cases(rng):
    cases = [(a, b, c) for a in VALUES for b in VALUES for c in VALUES]
    for _ in range(2000):                       # both limits, each side of each edge
        remaining, total = rng.getrandbits(64), rng.getrandbits(64)
        for edge in (remaining, MAX - total):
            for delta in (-1, 0, 1):
                cases.append((remaining, total, (edge + delta) & MAX))
    for _ in range(20000):
        pick = lambda: rng.choice(VALUES + [rng.getrandbits(64), rng.getrandbits(rng.randint(1, 63))])
        cases.append((pick(), pick(), pick()))
    rng.shuffle(cases)
    return cases


def unpack_states(blob, count):
    if len(blob) != 20 * count:
        return None
    return [struct.unpack_from("<iQQ", blob, 20 * i) for i in range(count)]


def kernel_tier(ctx, bpf_object: bytes, cases):
    receipt = ctx.receipt
    run, why = H.kernel_tier_decision()
    if not run:
        for name in ("kernel_verifier_accepts", "kernel_bytecode_semantics", "kernel_map_path"):
            receipt.check(name, why)
        return
    with tempfile.TemporaryDirectory(prefix="deltaos-kernel-") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "prog.bpf.o").write_bytes(bpf_object)
        (tmp / "cases.bin").write_bytes(b"".join(struct.pack("<3Q", *case) for case in cases))
        build = subprocess.run(["gcc", "-O2", "-Wall", str(H.TESTS / "kernel_check.c"), "-o",
                                str(tmp / "kernel_check"), "-lbpf", "-lelf", "-lz"],
                               capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise H.GraderError("kernel_check.c did not build: " + build.stderr[-600:])
        probe = subprocess.run([str(tmp / "kernel_check"), str(tmp / "prog.bpf.o"), str(tmp / "cases.bin"),
                                str(tmp / "answers.bin"), str(tmp / "xdp.bin"), str(XDP_CASES)],
                               capture_output=True, text=True, timeout=240)
        try:
            seen = json.loads(probe.stdout)
        except ValueError:
            raise H.GraderError("kernel_check produced no result: " + probe.stderr[-600:])
        answers = (tmp / "answers.bin").read_bytes() if (tmp / "answers.bin").is_file() else b""
        xdp = (tmp / "xdp.bin").read_bytes() if (tmp / "xdp.bin").is_file() else b""
    release = H.platform.release()
    receipt.kernel_profile = release
    if not seen.get("loaded"):
        receipt.check("kernel_verifier_accepts", False)
        raise H.Reject("kernel_verifier_rejected_program", stage=seen.get("stage"), log=probe.stderr[-1500:])
    receipt.check("kernel_verifier_accepts", True)
    receipt.add_evidence("KERNEL_ACCEPTED", "the kernel verifier loads the XDP program and the case runner",
                         "pass", f"Linux {release} {H.platform.machine()}")
    states = unpack_states(answers, len(cases))
    xdp_count = min(XDP_CASES, len(cases))
    xdp_states = unpack_states(xdp, xdp_count)
    if seen.get("bytecode_cases") != len(cases) or states is None or xdp_states is None:
        raise H.GraderError("kernel tier could not run the cases: " + json.dumps(seen)[:300])
    for case, got in zip(cases, states):
        if got != contract(*case):
            receipt.check("kernel_bytecode_semantics", False)
            raise H.Reject("wrong_state_in_bpf_bytecode", initial=list(case[:2]), amount=case[2],
                           expected=list(contract(*case)), actual=list(got))
    receipt.check("kernel_bytecode_semantics", True)
    receipt.add_evidence("TESTED", "the compiled BPF bytecode gives the contract's result on every case",
                         "pass", f"{len(cases)} cases executed by the Linux {release} BPF runtime "
                         "(BPF_PROG_TEST_RUN)", cases=len(cases))
    for case, got in zip(cases, xdp_states):
        if got != contract(*case):
            receipt.check("kernel_map_path", False)
            raise H.Reject("wrong_state_through_xdp_and_map", initial=list(case[:2]), amount=case[2],
                           expected=list(contract(*case)), actual=list(got))
    receipt.check("kernel_map_path", True)
    receipt.add_evidence("TESTED", "the XDP program charges a real BPF map value as the contract says",
                         "pass", f"{xdp_count} test packets through the XDP program, map written and read "
                         f"back, Linux {release}", cases=xdp_count)


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    source = H.read_artifact("quota.c")
    receipt.artifact("quota.c", source)
    sbx.put("quota.c", source)
    for name in ("driver.c", "prove.c", "bpf_adapter.c"):
        sbx.put(name, (H.TESTS / name).read_bytes())
    ctx.require_tool("gcc", "native_semantics")
    ctx.require_tool("clang", "bpf_bytecode_compilation")

    pre = sbx.run(["clang", "-target", "bpf", "-ffreestanding", "-E", "-P", "quota.c", "-o", "candidate.i"],
                  limits=H.TOOL_LIMITS, timeout=60)
    if not pre.ok:
        receipt.check("bpf_bytecode_compilation", False)
        raise H.Reject("does_not_preprocess_for_bpf", log=pre.text(1200))
    text = sbx.path("candidate.i").read_bytes()
    try:
        H.require_integer_c(text.decode("utf-8", "replace"), function="charge", structs=("budget",))
        receipt.check("plain_integer_c", True)
    except H.Reject:
        receipt.check("plain_integer_c", False)
        raise

    def fresh_text():
        sbx.put("candidate.i", text)

    fresh_text()
    bpf = sbx.run(["clang", *H.bpf_cflags(), "-c", "bpf_adapter.c", "-o", "prog.bpf.o"],
                  limits=H.TOOL_LIMITS, timeout=120)
    receipt.check("bpf_bytecode_compilation", bpf.ok)
    if not bpf.ok:
        raise H.Reject("does_not_compile_to_bpf", log=bpf.text(1200))
    bpf_object = sbx.path("prog.bpf.o").read_bytes()
    receipt.add_evidence("COMPILED", "charge compiles into the XDP program and the case runner", "pass",
                         "clang -target bpf -O2 -mcpu=v3; the preprocessed text is plain integer C")

    fresh_text()
    native = sbx.run(["gcc", "-std=c11", "-O2", "-ffreestanding", "-fno-stack-protector", "-Wall", "-Wextra",
                      "-x", "c", "-c", "candidate.i", "-o", "candidate.o"], limits=H.TOOL_LIMITS, timeout=120)
    receipt.check("native_compilation", native.ok)
    if not native.ok:
        raise H.Reject("does_not_compile", log=native.text(1200))
    try:
        H.require_freestanding(H.object_report(sbx, "candidate.o"), allowed_undefined=("_GLOBAL_OFFSET_TABLE_",))
        receipt.check("pure_function", True)
    except H.Reject:
        receipt.check("pure_function", False)
        raise

    if ctx.require_tool("cbmc", "proof_all_inputs"):
        fresh_text()
        proof = H.cbmc(sbx, ["prove.c", "candidate.i"], entry="harness", track=("remaining", "total", "amount"))
        scope = (f"CBMC {H.tool_version('cbmc')}; C semantics of the BPF-preprocessed text; "
                 "loops must finish within 16 iterations")
        if proof["status"] == "proved":
            receipt.check("proof_all_inputs", True)
            receipt.add_evidence("PROVED_WITHIN_MODEL",
                                 "for all 2^192 states and amounts charge returns and leaves exactly what the "
                                 "contract says, with no undefined behaviour", "pass", scope,
                                 properties=proof["properties"], seconds=proof["seconds"])
        elif proof["status"] == "refuted":
            receipt.check("proof_all_inputs", False)
            witness = proof["witness"]
            detail = {"property": proof["property"], "witness": witness}
            if all(k in witness for k in ("remaining", "total", "amount")):
                detail["expected"] = list(contract(witness["remaining"], witness["total"], witness["amount"]))
            raise H.Reject("counterexample_from_model_checker", **detail)
        else:
            receipt.check("proof_all_inputs", False)
            raise H.Reject("proof_did_not_complete", detail=proof)

    # Candidate code runs from here on.
    link = sbx.run(["gcc", "-O2", "driver.c", "candidate.o", "-o", "driver"], limits=H.TOOL_LIMITS, timeout=120)
    if not link.ok:
        raise H.Reject("does_not_link", log=link.text(1200))
    cases = build_cases(ctx.rng("cases"))
    run = sbx.run([str(sbx.path("driver"))], input=b"".join(struct.pack("<3Q", *c) for c in cases), timeout=60)
    states = unpack_states(run.stdout, len(cases)) if run.ok else None
    if states is None:
        receipt.check("native_semantics", False)
        raise H.Reject("candidate_crashed_or_hung", exit=run.returncode, timed_out=run.timed_out)
    for case, got in zip(cases, states):
        if got != contract(*case):
            receipt.check("native_semantics", False)
            raise H.Reject("wrong_state", initial=list(case[:2]), amount=case[2],
                           expected=list(contract(*case)), actual=list(got))
    receipt.check("native_semantics", True)
    receipt.extra["cases_executed"] = len(cases)
    receipt.add_evidence("TESTED", "charge returns and leaves the contract's state", "pass",
                         f"{len(cases)} cases on the same text built natively: the 13^3 edge grid, both sides "
                         "of both limits, 20000 fresh random cases", cases=len(cases))

    kernel_tier(ctx, bpf_object, cases)


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
