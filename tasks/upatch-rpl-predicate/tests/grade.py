#!/usr/bin/env python3
"""Grader for upatch-rpl-predicate.

Evidence, in the order it is collected:
  COMPILED             the predicate compiles into the fentry detector and the case runner
  PROVED_WITHIN_MODEL  CBMC: equal to the fix's bound for every n
  PROVED_WITHIN_MODEL  all 256 values of n executed natively (enumeration is a proof here)
  KERNEL_ACCEPTED      (kernel tier) the verifier loads the detector; it attaches by BTF
  TESTED in kernel     (kernel tier) all 256 values evaluated by the compiled bytecode

The candidate is preprocessed once for the BPF target and must be plain integer C.
Candidate code runs last. No RPL packet is ever sent.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/upatch-rpl-predicate"
MODEL = "c-decision-function/2"


def contract(n):
    return int(n + 1 > 127)


def kernel_tier(ctx, bpf_object: bytes):
    receipt = ctx.receipt
    run, why = H.kernel_tier_decision()
    if not run:
        for name in ("kernel_verifier_accepts", "kernel_detector_attaches", "kernel_bytecode_semantics"):
            receipt.check(name, why)
        return
    with tempfile.TemporaryDirectory(prefix="deltaos-kernel-") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "upatch.bpf.o").write_bytes(bpf_object)
        build = subprocess.run(["gcc", "-O2", "-Wall", str(H.TESTS / "kernel_check.c"), "-o",
                                str(tmp / "kernel_check"), "-lbpf", "-lelf", "-lz"],
                               capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise H.GraderError("kernel_check.c did not build: " + build.stderr[-600:])
        probe = subprocess.run([str(tmp / "kernel_check"), str(tmp / "upatch.bpf.o")],
                               capture_output=True, text=True, timeout=120)
    try:
        seen = json.loads(probe.stdout)
    except ValueError:
        raise H.GraderError("kernel_check produced no result: " + probe.stderr[-600:])
    release = H.platform.release()
    receipt.kernel_profile = release
    if not seen.get("loaded"):
        receipt.check("kernel_verifier_accepts", False)
        raise H.Reject("kernel_verifier_rejected_program", stage=seen.get("stage"), log=probe.stderr[-1500:])
    receipt.check("kernel_verifier_accepts", True)
    if seen.get("fentry_target"):
        if not seen.get("attached"):
            raise H.GraderError("the detector loaded but did not attach: " + json.dumps(seen)[:200])
        receipt.check("kernel_detector_attaches", True)
        receipt.add_evidence("KERNEL_ACCEPTED", "the kernel verifier loads the detector, and its fentry program "
                             "attaches to ipv6_rpl_srh_decompress()", "pass",
                             f"Linux {release} {H.platform.machine()}; attached, not driven by RPL traffic")
    else:
        receipt.check("kernel_detector_attaches", f"NOT_RUN: Linux {release} has no BTF for ipv6_rpl_srh_decompress")
        receipt.add_evidence("KERNEL_ACCEPTED", "the kernel verifier loads the case runner", "pass",
                             f"Linux {release}; the fentry target is missing from this kernel's BTF")
    answers = seen.get("answers")
    if not isinstance(answers, list) or len(answers) != 256 or any(a not in (0, 1) for a in answers):
        raise H.GraderError("kernel tier could not evaluate the predicate: " + json.dumps(seen)[:300])
    for n, got in enumerate(answers):
        if got != contract(n):
            receipt.check("kernel_bytecode_semantics", False)
            raise H.Reject("wrong_answer_in_bpf_bytecode", n=n, expected=contract(n), actual=got)
    receipt.check("kernel_bytecode_semantics", True)
    receipt.add_evidence("TESTED", "the compiled BPF bytecode gives the fix's answer for every n", "pass",
                         f"all 256 values executed by the Linux {release} BPF runtime (BPF_PROG_TEST_RUN)",
                         cases=256)


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    source = H.read_artifact("rpl_predicate.c")
    receipt.artifact("rpl_predicate.c", source)
    sbx.put("rpl_predicate.c", source)
    for name in ("driver.c", "prove.c", "upatch.bpf.c"):
        sbx.put(name, (H.TESTS / name).read_bytes())
    ctx.require_tool("gcc", "all_values_native")
    ctx.require_tool("clang", "bpf_bytecode_compilation")

    pre = sbx.run(["clang", "-target", "bpf", "-ffreestanding", "-E", "-P", "rpl_predicate.c", "-o",
                   "candidate.i"], limits=H.TOOL_LIMITS, timeout=60)
    if not pre.ok:
        receipt.check("bpf_bytecode_compilation", False)
        raise H.Reject("does_not_preprocess_for_bpf", log=pre.text(1200))
    text = sbx.path("candidate.i").read_bytes()
    try:
        H.require_integer_c(text.decode("utf-8", "replace"), function="rpl_fix_rejects")
        receipt.check("plain_integer_c", True)
    except H.Reject:
        receipt.check("plain_integer_c", False)
        raise

    def fresh_text():
        sbx.put("candidate.i", text)

    fresh_text()
    bpf = sbx.run(["clang", *H.bpf_cflags(), "-c", "upatch.bpf.c", "-o", "upatch.bpf.o"],
                  limits=H.TOOL_LIMITS, timeout=120)
    receipt.check("bpf_bytecode_compilation", bpf.ok)
    if not bpf.ok:
        raise H.Reject("does_not_compile_to_bpf", log=bpf.text(1200))
    bpf_object = sbx.path("upatch.bpf.o").read_bytes()
    receipt.add_evidence("COMPILED", "rpl_fix_rejects compiles into the fentry detector", "pass",
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
        proof = H.cbmc(sbx, ["prove.c", "candidate.i"], entry="harness", track=("n",))
        if proof["status"] == "proved":
            receipt.check("proof_all_inputs", True)
            receipt.add_evidence("PROVED_WITHIN_MODEL", "rpl_fix_rejects(n) is 1 exactly when n + 1 > 127, "
                                 "with no undefined behaviour", "pass",
                                 f"CBMC {H.tool_version('cbmc')}; C semantics of the BPF-preprocessed text",
                                 properties=proof["properties"], seconds=proof["seconds"])
        elif proof["status"] == "refuted":
            receipt.check("proof_all_inputs", False)
            n = proof["witness"].get("n")
            raise H.Reject("counterexample_from_model_checker", property=proof["property"], n=n,
                           expected=contract(n) if isinstance(n, int) else None)
        else:
            receipt.check("proof_all_inputs", False)
            raise H.Reject("proof_did_not_complete", detail=proof)

    # Candidate code runs from here on.
    link = sbx.run(["gcc", "-O2", "driver.c", "candidate.o", "-o", "driver"], limits=H.TOOL_LIMITS, timeout=120)
    if not link.ok:
        raise H.Reject("does_not_link", log=link.text(1200))
    run = sbx.run([str(sbx.path("driver"))], timeout=30)
    if not run.ok or len(run.stdout) != 4 * 256:
        receipt.check("all_values_native", False)
        raise H.Reject("candidate_crashed_or_hung", exit=run.returncode, timed_out=run.timed_out)
    for n, got in enumerate(struct.unpack("<256i", run.stdout)):
        if got != contract(n):
            receipt.check("all_values_native", False)
            raise H.Reject("wrong_answer", n=n, expected=contract(n), actual=got)
    receipt.check("all_values_native", True)
    receipt.add_evidence("PROVED_WITHIN_MODEL", "the predicate matches the fix for every n", "pass",
                         "all 256 values of n executed natively: the domain is small enough to enumerate",
                         cases=256)

    kernel_tier(ctx, bpf_object)


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
