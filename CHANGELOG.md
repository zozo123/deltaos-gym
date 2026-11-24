# Changelog

## 1.0.0 (2026-11-24)

The graders are rewritten. Version 0.5 rejected its 20 planted mutants and accepted
27 of 27 further wrong candidates (`qa/reports/v05-escape-matrix.json`).

**Graders**
- One trusted harness (`harness/deltaos_harness.py`), vendored into every task: candidate
  code never runs in the grader's process; as root it runs under another uid that can
  neither read `tests/` nor write the verdict; everything it starts is killed before the
  verdict; fresh hidden cases per episode from a recorded seed; fail closed.
- Receipts (`receipt.json`, `contracts/receipt.schema.json`): every claim with its
  evidence class and scope, the artifact's SHA-256, the seed, a digest of the grader.
- BPF tasks: the candidate is preprocessed once for the BPF target and must be plain
  integer C; CBMC proves it against the contract for every input; an optional kernel
  tier loads it, runs every case through the compiled bytecode and attaches it for real.
- `vfs-crash-atomicity`: model checking against a stated Linux persistence model
  (fsync errors reported once, close after fsync, directory fsync), every schedule of
  short writes, interrupted writes and up to two I/O errors for small payloads.
- `fd-capability-boundary`: real launches; the worker is a setuid observer under its own
  uid; the caller's descriptor table is read from `/proc` before and after.
- `probe-design`: the solver runs sandboxed; answers are type-checked; fresh instances.

**Tasks**
- New: `upatch-rpl-predicate`, from shirudo's tutorial on turning a kernel fix
  (CVE-2026-63984) into a BPF detector.
- All tasks are Harbor schema 1.4 with a separate verifier image.

**Controls and QA**
- `qa/controls/<task>/`: 65 honest mistakes and exploits (45 that v0.5 never saw), plus 17
  correct alternatives that must be accepted. `scripts/release_qa.py` runs everything.

**Step environment**
- Rewards a justified answer, not a lucky one; abstaining is right when nothing
  affordable can separate the remaining causes; seeded resets; baseline policies;
  the hidden cause is no longer accepted on the command line.

**Removed**
- Pricing and pitch material, superseded QA reports and scripts.

## 0.5.0 (2026-11-23)

First research prototype: five Harbor-style tasks, a step environment, 20 planted mutants.
