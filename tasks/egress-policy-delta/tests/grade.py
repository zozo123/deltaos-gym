#!/usr/bin/env python3
"""Grader for egress-policy-delta.

Evidence, in the order it is collected:
  COMPILED             the policy compiles into the cgroup/connect4 BPF object
  PROVED_WITHIN_MODEL  CBMC: equal to the contract for all 2^113 inputs, no undefined behaviour
  TESTED               the same text, built natively, answers every case
  KERNEL_ACCEPTED      (kernel tier) the running kernel's verifier loads the object
  TESTED in kernel     (kernel tier) the bytecode answers every case; real connect() calls

One text for every tier: the candidate is preprocessed for the BPF target once, and
must be plain integer C (no sizeof, floating point, addresses, asm, builtins), the
part of C on which x86-64 and BPF agree. So the program that is proved is the program
the kernel runs. Candidate code runs last, after everything has been built and proved.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/egress-policy-delta"
MODEL = "c-decision-function/2"
ALLOW = (10042, 0x0A040209, 443, 6)       # uid, IPv4 10.4.2.9, port, TCP
WIDTHS = (32, 32, 16, 32)
BASELINE = (10042, 0x0A040235, 53, 17)    # what bpf_adapter.c passes as previously_allowed


def contract(uid, ip, port, proto, prior):
    return int(bool(prior) or (uid, ip, port, proto) == ALLOW)


def flip(flow, picks):
    values = list(flow)
    for field, bit in picks:
        values[field] ^= 1 << bit
    return tuple(values)


def build_cases(rng):
    cases = []
    for prior in (0, 1):                                    # regression grid
        for uid in (10042, 10043, 0, 0xFFFFFFFF):
            for ip in (0x0A040209, 0x0A040208, 0x0A04020A, 0x0A040200,
                       0x0A0402FF, 0x7F000001, 0xFFFFFFFF, 0):
                for port in (0, 53, 80, 443, 444, 65535):
                    for proto in (6, 17, 0, 255):
                        cases.append((uid, ip, port, proto, prior))
    bits = [(field, bit) for field, width in enumerate(WIDTHS) for bit in range(width)]
    for index, first in enumerate(bits):                    # every 1- and 2-bit neighbour
        cases.append(flip(ALLOW, [first]) + (0,))
        for second in bits[index + 1:]:
            cases.append(flip(ALLOW, [first, second]) + (0,))
    special = ([10042, 10043, 0, 0xFFFFFFFF], [0x0A040209, 0x0A040208, 0x0A0402FF, 0x0A040235],
               [443, 53, 80, 0], [6, 17, 0, 255])
    for _ in range(20000):                                  # fresh for this episode
        kind = rng.randrange(3)
        if kind == 0:
            flow = tuple(rng.getrandbits(width) for width in WIDTHS)
        elif kind == 1:
            flow = flip(ALLOW, rng.sample(bits, rng.randint(1, 8)))
        else:
            flow = tuple(rng.choice(pool + [rng.getrandbits(width)])
                         for pool, width in zip(special, WIDTHS))
        cases.append(flow + (rng.randrange(2),))
    return cases


def kernel_flows():
    """Flows a real socket can produce: TCP or UDP, a uid we can switch to."""
    flows = []
    for uid in (10042, 10043, 75578, 0):                    # 75578 = 10042 + 65536
        for ip in (0x0A040209, 0x0A040208, 0x0A04020A, 0x0B040209, 0x0A040235, 0x7F000001):
            for port in (443, 444, 53, 80):
                for proto in (6, 17):
                    flows.append((uid, ip, port, proto))
    return flows


def kernel_tier(ctx, bpf_object: bytes, cases):
    receipt = ctx.receipt
    run, why = H.kernel_tier_decision()
    if not run:
        for name in ("kernel_verifier_accepts", "kernel_bytecode_semantics", "kernel_connect_semantics"):
            receipt.check(name, why)
        return
    flows = kernel_flows()
    with tempfile.TemporaryDirectory(prefix="deltaos-kernel-") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "prog.bpf.o").write_bytes(bpf_object)
        (tmp / "cases.bin").write_bytes(b"".join(struct.pack("<5I", *case) for case in cases))
        build = subprocess.run(["gcc", "-O2", "-Wall", str(H.TESTS / "kernel_check.c"), "-o",
                                str(tmp / "kernel_check"), "-lbpf", "-lelf", "-lz"],
                               capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise H.GraderError("kernel_check.c did not build: " + build.stderr[-600:])
        probe = subprocess.run([str(tmp / "kernel_check"), str(tmp / "prog.bpf.o"), str(tmp / "cases.bin"),
                                str(tmp / "answers.bin")],
                               input="".join("%d %d %d %d\n" % f for f in flows),
                               capture_output=True, text=True, timeout=240)
        try:
            seen = json.loads(probe.stdout)
        except ValueError:
            raise H.GraderError("kernel_check produced no result: " + probe.stderr[-600:])
        answers = (tmp / "answers.bin").read_bytes() if (tmp / "answers.bin").is_file() else b""
    release = H.platform.release()
    receipt.kernel_profile = release
    if not seen.get("loaded"):
        receipt.check("kernel_verifier_accepts", False)
        receipt.add_evidence("KERNEL_ACCEPTED", "the kernel verifier loads the BPF object", "fail",
                             f"Linux {release}", stage=seen.get("stage"))
        raise H.Reject("kernel_verifier_rejected_program", stage=seen.get("stage"), log=probe.stderr[-1500:])
    receipt.check("kernel_verifier_accepts", True)
    receipt.add_evidence("KERNEL_ACCEPTED", "the kernel verifier loads the cgroup/connect4 program",
                         "pass", f"Linux {release} {H.platform.machine()}")
    if seen.get("bytecode_cases") != len(cases) or len(answers) != 4 * len(cases):
        raise H.GraderError("kernel tier could not run the cases: " + json.dumps(seen)[:300])
    for case, got in zip(cases, struct.unpack("<%di" % len(cases), answers)):
        want = contract(*case)
        if got != want:
            receipt.check("kernel_bytecode_semantics", False)
            raise H.Reject("wrong_decision_in_bpf_bytecode", case=list(case), expected=want, actual=got)
    receipt.check("kernel_bytecode_semantics", True)
    receipt.add_evidence("TESTED", "the compiled BPF bytecode gives the contract's answer on every case",
                         "pass", f"{len(cases)} cases executed by the Linux {release} BPF runtime "
                         "(BPF_PROG_TEST_RUN)", cases=len(cases))
    decisions = seen.get("decisions")
    if not seen.get("attached") or not isinstance(decisions, list) or len(decisions) != len(flows) \
            or any(d not in (0, 1) for d in decisions):
        raise H.GraderError("kernel tier could not attach or measure: " + json.dumps(seen)[:300])
    for flow, got in zip(flows, decisions):
        want = contract(*flow, int(flow == BASELINE))
        if got != want:
            receipt.check("kernel_connect_semantics", False)
            raise H.Reject("wrong_decision_in_kernel", flow=list(flow), expected=want, actual=got)
    receipt.check("kernel_connect_semantics", True)
    receipt.add_evidence("TESTED", "real connect() calls follow the contract with the program attached",
                         "pass", f"{len(flows)} connect() calls (TCP and UDP, 4 uids) from a cgroup with the "
                         f"program attached, Linux {release}", flows=len(flows))


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    source = H.read_artifact("policy.c")
    receipt.artifact("policy.c", source)
    sbx.put("policy.c", source)
    for name in ("driver.c", "prove.c", "bpf_adapter.c"):
        sbx.put(name, (H.TESTS / name).read_bytes())
    ctx.require_tool("gcc", "native_semantics")
    ctx.require_tool("clang", "bpf_bytecode_compilation")

    # One text for every tier: the candidate as the BPF target sees it.
    pre = sbx.run(["clang", "-target", "bpf", "-ffreestanding", "-E", "-P", "policy.c", "-o", "candidate.i"],
                  limits=H.TOOL_LIMITS, timeout=60)
    if not pre.ok:
        receipt.check("bpf_bytecode_compilation", False)
        raise H.Reject("does_not_preprocess_for_bpf", log=pre.text(1200))
    text = sbx.path("candidate.i").read_bytes()
    try:
        H.require_integer_c(text.decode("utf-8", "replace"), function="policy_decide")
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
    receipt.add_evidence("COMPILED", "policy_decide compiles into the cgroup/connect4 BPF object", "pass",
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
        proof = H.cbmc(sbx, ["prove.c", "candidate.i"], entry="harness",
                       track=("uid", "ip", "port", "proto", "prior"))
        scope = (f"CBMC {H.tool_version('cbmc')}; C semantics of the BPF-preprocessed text, "
                 "previously_allowed in {0,1}; loops must finish within 16 iterations")
        if proof["status"] == "proved":
            receipt.check("proof_all_inputs", True)
            receipt.add_evidence("PROVED_WITHIN_MODEL",
                                 "for all 2^113 inputs policy_decide equals the contract and has no "
                                 "undefined behaviour", "pass", scope, properties=proof["properties"],
                                 seconds=proof["seconds"])
        elif proof["status"] == "refuted":
            receipt.check("proof_all_inputs", False)
            witness = proof["witness"]
            detail = {"property": proof["property"], "witness": witness}
            if all(k in witness for k in ("uid", "ip", "port", "proto", "prior")):
                detail["expected"] = contract(witness["uid"], witness["ip"], witness["port"],
                                              witness["proto"], witness["prior"])
            raise H.Reject("counterexample_from_model_checker", **detail)
        else:
            receipt.check("proof_all_inputs", False)
            raise H.Reject("proof_did_not_complete", detail=proof)

    # Candidate code runs from here on.
    link = sbx.run(["gcc", "-O2", "driver.c", "candidate.o", "-o", "driver"], limits=H.TOOL_LIMITS, timeout=120)
    if not link.ok:
        raise H.Reject("does_not_link", log=link.text(1200))
    cases = build_cases(ctx.rng("cases"))
    blob = b"".join(struct.pack("<5I", *case) for case in cases)
    run = sbx.run([str(sbx.path("driver"))], input=blob, timeout=60)
    if not run.ok or len(run.stdout) != 4 * len(cases):
        receipt.check("native_semantics", False)
        raise H.Reject("candidate_crashed_or_hung", exit=run.returncode, timed_out=run.timed_out)
    for case, got in zip(cases, struct.unpack("<%di" % len(cases), run.stdout)):
        want = contract(*case)
        if got != want:
            receipt.check("native_semantics", False)
            raise H.Reject("wrong_decision", case=list(case), expected=want, actual=got)
    receipt.check("native_semantics", True)
    receipt.extra["cases_executed"] = len(cases)
    receipt.add_evidence("TESTED", "policy_decide returns the contract's answer", "pass",
                         f"{len(cases)} cases on the same text built natively: regression grid, "
                         "all 1- and 2-bit neighbours of the allowed flow, 20000 fresh random cases",
                         cases=len(cases))

    kernel_tier(ctx, bpf_object, cases)


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
