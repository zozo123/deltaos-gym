# DeltaOS Gym and shirudo

[shirudo](https://shirudo.dev) is an open-source (BSD-2-Clause) eBPF security platform.
A Linux target runs only the BPF its operator signed, every load and unload is measured
into the TPM, and functionality ships as signed micropatches, "upatches", that targets
pull from OCI registries. Its site lists agents among the authors of upatches, and
live-patching kernel bugs among the uses.

This project is independent of shirudo and not affiliated with it. This page explains
why the two fit together and what in this repository is built for that.

## The gap shirudo names itself

shirudo's guarantee is about origin and record: which key signed the code, where it
attached, and that the change is in the measurement log. Its documentation is exact
about where that stops. Of the signature it says: "it shows who built the upatch, not
that the upatch is correct"
([upatch concepts](https://docs.shirudo.dev/upatches/learn/concepts.html)). The kernel
verifier does not close that gap either. It checks that a program is safe to run, and a
program that drops every packet is perfectly safe.

So three questions stand between a kernel fix and a fleet:

| Question | Who answers it |
|---|---|
| Is this BPF safe to run in the kernel? | the kernel verifier |
| Who built it, where is it attached, is the change on record? | shirudo (signature, attach metadata, TPM) |
| Does it do what the fix requires, and nothing else? | nobody, by default |

The third question is what this gym grades. If agents are going to write upatches, that
is the one that needs an answer before the operator's key is used.

## What a upatch is, in gym terms

A upatch that mitigates a kernel bug is a predicate at an attach point: which calls
should be refused or recorded. shirudo's tutorial
[From a kernel fix to a upatch](https://docs.shirudo.dev/upatches/learn/kernel-fix-tutorial.html)
derives that predicate from the upstream fix: the fix says which inputs are dangerous,
and that condition becomes the program.

That is a behavioural delta with a known right answer, which is the shape of every task
here: change exactly this, preserve everything else, and show evidence for both.

## What is in this repository

**A task taken from that tutorial.** `tasks/upatch-rpl-predicate` uses the tutorial's
example (CVE-2026-63984, an 8-bit overflow in the IPv6 RPL routing header code). The
agent writes the predicate the detector needs. The grader then collects:

- `PROVED_WITHIN_MODEL`: all 256 values of the argument executed natively, plus a CBMC
  proof of the same statement;
- `KERNEL_ACCEPTED`: the detector, an `fentry` program on `ipv6_rpl_srh_decompress`,
  loads and attaches on a real kernel;
- `TESTED` in the kernel: a `SEC("syscall")` test-run program evaluates the compiled
  predicate for all 256 values inside the kernel's BPF runtime.

The dangerous branch itself is not driven with packets: on a kernel without the fix
that would trigger the bug. The receipt says so. Evidence for that branch comes from
enumeration and proof, which is the general lesson: some properties of a mitigation
cannot be tested safely on the system it protects.

One more thing the receipt does not answer: reachability. The unfixed kernel already
refuses `n = 255` before the hooked function is called, so a predicate that is wrong
only at 255 can never be observed there. The task's contract is the tutorial's
predicate over all 256 values; whether an input can occur is a separate question.

**A gate for the signing step.** `scripts/receipt_gate.py` exits 0 only if a receipt is
valid, passed, produced under uid separation, matches the SHA-256 of the file you are
about to sign, and carries the evidence classes you require:

```sh
python3 scripts/receipt_gate.py receipt.json rpl_predicate.c \
    --require PROVED_WITHIN_MODEL --require KERNEL_ACCEPTED \
  && shirudo build ...
```

**The same program type shirudo uses for self-tests.** shirudo lets a upatch carry a
test-run program in `SEC("syscall")` that runs once at load; a negative return fails
the load. The gym's kernel tier evaluates candidates through that same program type.
For a small domain the check a grader runs could ship inside the upatch, so every
target re-establishes it on its own kernel at load time.

## Where this could go

These are proposals. None of them is implemented here.

1. **Every kernel fix is a task with a known answer.** A bound-fix commit gives an old
   predicate and a new one. The mitigation must flag exactly the inputs the new code
   refuses and the old code let through. Fixes arrive every week, so the task stream is
   held out by construction, and shirudo's `upatches/kernel-cve/sources` are reference
   solutions written by people.
2. **Receipts next to packages.** A receipt names the artifact by digest. Published as
   an OCI referrer beside the `.bee` package, it would let an operator's policy say:
   sign only what has a receipt of class X on kernel Y.
3. **Attested grading.** The weak point of any benchmark number is who ran the grader.
   On a shirudo target the grader's kernel probes are signed upatches and the TPM quote
   lists what was loaded. A receipt bound to that quote is a result a third party can
   check.
4. **Enforce what the gym tests.** `fd-capability-boundary` checks that a launcher
   passes exactly one descriptor across `exec`. shirudo lists sandboxes for LLM agents
   among its uses; the same property could be enforced on the running system by a
   hardening upatch while the gym checks the launchers that are supposed to honour it.
