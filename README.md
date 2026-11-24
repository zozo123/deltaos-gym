# DeltaOS Gym

A small open benchmark for AI agents that change systems code, and a record of how
its first graders were fooled. An [islo.dev](https://islo.dev) project.

Each task hands the agent a piece of real systems code with a defect and a contract:
change exactly this, keep everything else. A separate verifier decides, and writes a
receipt that says what its decision rests on.

**Read the write-up: https://zozo123.github.io/deltaos-gym/**

## The short version

Version 0.5 shipped with 20 planted bugs and rejected all of them. Then 27 more wrong
candidates were written against it, 14 ordinary mistakes and 13 attempts to get the
reward without solving the task. **The v0.5 graders gave full reward to all 27**
([table](qa/reports/v05-escape-matrix.json)). A few of the ways:

- `#ifdef __bpf__`: the grader tested the x86 build and the kernel got a different
  program. Loaded into Linux 7.1.4, the accepted candidate let through 192 of 192 test
  connections; the contract allows 2.
- The candidate was loaded into the grader's own process, so it wrote `reward.txt`
  itself and called `_exit(0)`.
- A backdoor on one input in 2^113 passed 25,000 random tests.
- The crash model let a failed `fsync` be repaired by calling it again.
- Requirements in the task text (propagate the worker's exit status, survive `EINTR`)
  had no test.

Version 1.0 replaces the graders. Results on a disposable 16-vCPU Linux 7.1.4 VM, as
root with candidates under another uid, kernel tier on
([report](qa/reports/release-report.json)):

| | |
|---|---|
| Tasks | 6 |
| Wrong candidates accepted | 0 of 71 (65 negative controls and 6 starters), over 355 graded runs on fresh seeds |
| Correct, differently written solutions accepted | 85 of 85 runs (17 controls, 5 seeds each) |
| Receipts valid against the schema | 470 of 470 |
| The same QA in CI on a GitHub runner | passes on Linux 7.0.0-1014-aws, kernel tier on ([report](qa/reports/ci-github-runner.json)) |
| Harbor 0.27.0 | reference agent 1.0 and do-nothing agent 0.0 on all 6 tasks, each graded in its own verifier container with the candidate under another uid; `harbor lint` clean ([report](qa/reports/harbor-e2e.json)) |

While the new graders were being built, an independent pass found that preprocessing
the candidate once for BPF was not enough: `sizeof(long double)` is 16 on x86-64 and 8
for BPF, so one text can still be two programs. Decision functions must now be plain
integer C, the part of C on which the two targets agree.

## Reproduce the numbers

Every number above comes from a file in `qa/reports/`, and each has a script:

| Report | How to regenerate (Linux, Docker) |
|---|---|
| `release-report.json` | `docker run --rm --privileged -v "$PWD":/gym -w /gym deltaos-dev python3 scripts/release_qa.py --kernel` |
| `v05-escape-matrix.json` | `sh scripts/legacy_escape_matrix.sh > v05.tsv && python3 scripts/escape_matrix_report.py v05.tsv` (uses the original v0.5 graders kept in [`legacy/`](legacy)) |
| `kernel-demo-egress.json` | `docker run --rm --privileged -v "$PWD":/gym:ro deltaos-dev python3 /gym/qa/kernel_demo.py /gym` |
| `harbor-e2e.json` | `scripts/harbor_e2e.sh OUT [--public-network] && python3 scripts/harbor_summary.py OUT` |
| `ci-github-runner.json` | the `release QA` workflow's artifact, on every push |

The legacy matrix also shows that v0.5 accepted 6 of the 11 wrong candidates written later,
and rejected one correct solution (a launcher built on `posix_spawn`).

## What a pass means

The reward is one bit. The receipt lists each claim with the class of evidence behind
it ([details](docs/evidence.md)):

| Class | Example from the egress task's reference |
|---|---|
| `COMPILED` | the policy compiles into the `cgroup/connect4` BPF object |
| `TESTED` | 27,864 cases on the BPF-preprocessed source |
| `PROVED_WITHIN_MODEL` | CBMC: equal to the contract for all 2^113 inputs, no undefined behaviour |
| `KERNEL_ACCEPTED` | the Linux 7.1.4 verifier loads the program |
| `TESTED` (in kernel) | the compiled bytecode on all 27,864 cases; 192 real `connect()` calls through the attached program |

No class implies another. The kernel verifier loaded every wrong egress candidate too.

## Tasks

| Task | The agent fixes | How it is checked |
|---|---|---|
| [`egress-policy-delta`](tasks/egress-policy-delta) | a BPF egress policy that opens a whole /24 | cases, proof over all inputs, kernel tier |
| [`quota-overflow-preservation`](tasks/quota-overflow-preservation) | 64-bit accounting that narrows and wraps | cases, proof over all inputs, kernel tier |
| [`upatch-rpl-predicate`](tasks/upatch-rpl-predicate) | the predicate of a kernel-bug detector, from shirudo's tutorial | all 256 values, proof, kernel tier |
| [`vfs-crash-atomicity`](tasks/vfs-crash-atomicity) | `publish()` that can lose or tear a file on a crash | every fault schedule within bounds, every crash cut |
| [`fd-capability-boundary`](tasks/fd-capability-boundary) | a launcher that leaks descriptors across `exec` | real launches observed from outside |
| [`probe-design`](tasks/probe-design) | a solver for cheapest distinguishing probe sets | exact oracle on fresh instances |

There is also a small step environment for active diagnosis in [`gym_runtime/`](gym_runtime):
it scores whether an answer was justified by the observations, not only whether it was right.

## shirudo

[shirudo](https://shirudo.dev) signs and measures the BPF a machine runs and ships
fixes as signed "upatches", with agents among their intended authors. Its docs are
clear that a signature says who built a upatch, not whether it is correct. That second
question is what this gym grades. One task is taken from shirudo's tutorial, and
`scripts/receipt_gate.py` is a gate for the step before a signature.
[More](docs/shirudo.md). This project is independent of shirudo.

## Run it

```sh
docker build -t deltaos-dev -f qa/Dockerfile.dev qa

# one task: the reference, the starter and every control
docker run --rm -v "$PWD":/gym -w /gym deltaos-dev python3 scripts/run_controls.py egress-policy-delta

# one candidate of your own
docker run --rm -v "$PWD":/gym -w /gym deltaos-dev python3 scripts/grade_local.py egress-policy-delta my_policy.c --print

# everything, 5 fresh seeds each
docker run --rm -v "$PWD":/gym -w /gym deltaos-dev python3 scripts/release_qa.py

# with the kernel tier: loads candidate BPF into the kernel, so only in a disposable VM
docker run --rm --privileged -v "$PWD":/gym -w /gym deltaos-dev python3 scripts/release_qa.py --kernel

# as Harbor tasks
harbor run -p tasks/vfs-crash-atomicity -a oracle
```

The graders compile and execute what they are given. Run candidates you did not write
only in a sandbox you can throw away, such as an [islo.dev](https://islo.dev) sandbox or
a disposable VM.

## Layout

```
harness/deltaos_harness.py   the trusted grader core (one file, standard library only)
tasks/<task>/                Harbor task: instruction.md, environment/, solution/, tests/
qa/controls/<task>/          what the graders are tested with: m* mistakes, x* exploits, p* correct alternatives
qa/reports/                  measured results this README and the site quote
scripts/                     grade_local, run_controls, release_qa, receipt_gate, validate_receipt, build_site
gym_runtime/                 reset/step diagnosis environment
docs/                        design, evidence classes, grader threat model, shirudo, roadmap; the site
```

## Limits

- Six tasks is a seed. The graders and the method are the contribution.
- The crash model is small and stated; it is not ext4.
- Proofs are within CBMC's semantics of C.
- Without root there is no second user to run the candidate as; receipts then say `same-uid`.
- Receipts are unsigned JSON.

[Design](docs/design.md) · [Evidence](docs/evidence.md) · [Grader threat model](docs/grader-threat-model.md) ·
[Research program](docs/research-program.md) · [Not built yet](docs/roadmap.md)

MIT licensed. BPF sources loaded into a kernel are `GPL-2.0 OR MIT`.
