# What the graders defend against

A gym that pays for a `1` in `reward.txt` will be searched for the cheapest way to
produce that `1`. This page lists the ways we know, what stops each, and what is left.

## The candidate is hostile code

| Attempt | v0.5 | Now |
|---|---|---|
| Overwrite `reward.txt` from code loaded into the grader's process (`atexit`, constructor) | reward 1 | Candidate code is never loaded into the grader. It runs in a sandbox process; as root, under another uid that cannot write the verdict directory. |
| Write `reward.txt` and `_exit(0)` before the grader writes its own | reward 1 | Same. The grader also writes `0` first and replaces it atomically at the end. |
| Print the verdict (`{"passed": true}`) from the process that hosts the candidate | reward 1 | Nothing a candidate process prints is a verdict. Graders compare raw answers with the contract themselves. |
| Leave a daemon that rewrites the verdict after the grader exits | reward 1 | The daemon cannot write the directory, and every process of the sandbox uid is killed before the verdict is written. |
| Read the grader's oracle and call it | reward 1 | `tests/` is mode 0700 and owned by root; the sandbox uid cannot read it. |
| Forge the "worker ran" receipt from environment variables | reward 1 | The worker is a setuid observer binary; only by executing it can anything be written where receipts live. Paths and nonces are compiled in, not passed through the candidate. |
| `#ifdef __bpf__`: one program for the test, another for the kernel | reward 1 | The candidate is preprocessed for the BPF target once; that one text is tested, proved and compiled. |
| One text, two programs: `sizeof(long double)` is 16 on x86-64 and 8 for BPF; a local's address starts with `0xff` only in the kernel | found during the rewrite | Decision functions must be plain integer C (no `sizeof`, floating point, addresses, asm or builtins), the part of C on which the targets agree. The kernel tier also runs the compiled bytecode on every case. |
| A backdoor on one input in 2^113 | reward 1 | CBMC proves equivalence to the contract for every input, or returns the input. |
| Inline assembly that makes raw system calls from inside the native test | not tried | Rejected by the plain-integer-C rule; for `publish()`, only the `vfs_api` calls and `mem*` may be used. |
| Behave until call N, then misbehave | reward 1 | Decision functions must be freestanding objects with no writable state. |
| Symlink the artifact to a file the grader can read | not tried | Artifacts are opened with `O_NOFOLLOW`, must be regular files, and are size-capped. |

## The candidate is an honest mistake

A grader that only catches attacks still pays for bugs. The 14 `m05+` controls are
ordinary mistakes v0.5 accepted: a 16-bit uid compare, `fsync` after `close`, retrying
a failed `fsync`, restarting a write from byte 0 on `EINTR`, ignoring the worker's exit
status, never looking at `authorized_fd`. Each is now rejected with a counterexample.

## The grader is wrong in the other direction

Rejecting correct work is also a grading error. Every task has `p*` controls: correct
implementations written differently from the reference. Release QA requires all of them
to be accepted on every seed.

## What is left

- Same-uid runs. Without root there is no second user. Local runs report
  `isolation.mode: "same-uid"` and are for trusted fixtures only.
- The verifier container shares a kernel with its host. A kernel exploit in candidate
  code is out of scope; run verifiers in VMs you can throw away.
- The trusted computing base is the harness (one file), each task's `tests/`, the
  compilers, CBMC and the kernel. A proof is a statement about CBMC's semantics of C,
  not about the machine code a compiler emits.
- Receipts are unsigned JSON. `scripts/receipt_gate.py` checks that a receipt matches a
  file, not who produced it.
- The graders are public. Nothing here depends on a secret test set: hidden cases are
  drawn fresh from a per-episode seed, and the strongest tiers do not sample at all.
