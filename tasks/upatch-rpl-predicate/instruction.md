# Write the predicate of a kernel-bug detector

This task follows the example in shirudo's tutorial
[From a kernel fix to a upatch](https://docs.shirudo.dev/upatches/learn/kernel-fix-tutorial.html),
which turns an upstream kernel fix into a BPF detector ("upatch"). This gym is not
affiliated with shirudo; the facts below are the tutorial's.

**The bug (CVE-2026-63984).** `ipv6_rpl_srh_rcv()` derives `n` from a received IPv6 RPL
routing header and calls `ipv6_rpl_srh_decompress()`, which stores `((n + 1) * 16) >> 3`
in an 8-bit header length. From `n = 127` on the value no longer fits, and the routing
header of the forwarded packet is corrupted. The fix changes one bound in
`ipv6_rpl_srh_rcv()` from `(n + 1) > 255` to `(n + 1) > 127`.

**The detector.** An `fentry` program on `ipv6_rpl_srh_decompress()` (whose fourth
argument is `unsigned char n`) counts every call, and counts separately the calls the
fix rejects. You write the part that decides which calls those are.

Edit only `/workspace/rpl_predicate.c`. Keep the signature:

```c
int rpl_fix_rejects(unsigned char n);
```

Return `1` exactly for the values of `n` the fix rejects, `0` for all others. The
current version is wrong for one value.

## Rules for the source

The judge proves and tests this file natively, and the kernel runs it as BPF. So that
both are the same program, the file must be plain integer C: integer types, constants,
operators, `if`/`switch` and functions you define; no `sizeof`, floating point, arrays,
string literals, address-of (`&x`), function names used as values, inline assembly,
builtins, attributes, pragmas, `extern` declarations or writable `static` state; no
undefined behaviour.

## What the judge does

- Compiles the detector for BPF with your predicate inside.
- Proves with CBMC that the predicate equals the fix's bound for every `n`, and runs
  all 256 values natively.
- In a disposable VM with the kernel tier on: loads the detector (the kernel verifier
  decides), attaches it to `ipv6_rpl_srh_decompress()`, and has the kernel evaluate the
  compiled predicate for all 256 values. It never sends an RPL packet: on a kernel
  without the fix that would run the vulnerable code.

This is a warm-up task. The point is the evidence a detector should come with.
