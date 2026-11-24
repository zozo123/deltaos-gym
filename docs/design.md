# Design

## An episode

The agent gets a small piece of real systems code with a stated defect and a contract:
change exactly this behaviour, keep everything else. It edits one artifact. A separate
verifier, which the agent never sees running, decides.

A solution is judged on three things:

1. **Target change.** The required behaviour holds.
2. **Preservation.** Everything the contract did not ask to change is unchanged.
3. **Evidence.** The receipt names, claim by claim, how each was established
   ([evidence classes](evidence.md)).

The reward is binary. Performance is not scored.

## Rules every grader follows

They are enforced by one file, `harness/deltaos_harness.py`, vendored into each task.

1. Candidate code never runs in the grader's process. When the grader is root, the
   candidate also runs as a different user that cannot read `tests/` or write the
   verdict directory.
2. The verdict is computed by the grader from data. Nothing a candidate prints is a verdict.
3. Hidden cases are drawn fresh per episode from a seed recorded in the receipt.
4. The artifact that is tested is the artifact that ships. For BPF tasks the source is
   preprocessed for the BPF target once, must be plain integer C (where x86-64 and BPF
   agree), and that text is tested, proved and compiled.
5. Every enforced requirement is written in the task's `instruction.md`.
6. Fail closed: a crash, a timeout or a missing required tool is reward 0.
7. Graders are public. Soundness may not depend on a secret.

## How a task is checked

| Task | Artifact | Checked by |
|---|---|---|
| `egress-policy-delta` | C decision function inside a `cgroup/connect4` program | cases on the BPF-preprocessed source; CBMC over all 2^113 inputs; kernel tier: verifier, bytecode on every case, real `connect()` calls |
| `quota-overflow-preservation` | C accounting step on a BPF map value | cases; CBMC over all 2^192 inputs; kernel tier: verifier, XDP test runs |
| `upatch-rpl-predicate` | predicate of a kernel-bug detector (from shirudo's tutorial) | all 256 values natively; CBMC; kernel tier: `fentry` attach, all 256 values in the kernel |
| `vfs-crash-atomicity` | C `publish()` over a syscall-like API | every fault schedule within bounds, every crash cut, against a stated persistence model |
| `fd-capability-boundary` | C launcher across `fork`/`exec` | real launches; the child's descriptor table read by a setuid observer, the caller's from `/proc` |
| `probe-design` | Python solver for minimum-cost distinguishing probe sets | exact oracle on fixed, directed and fresh random instances |

`qa/controls/<task>/` holds what each grader is itself tested with: honest mistakes
(`m*`), exploits (`x*`) and correct alternatives (`p*`). See
[what the graders defend against](grader-threat-model.md).

## The step environment

`gym_runtime/` is a small `reset`/`step` environment for active diagnosis: a hidden
root cause, probes with costs and possibly overlapping readings, a budget. It scores
the answer and how it was reached: a correct answer that the observations did not pin
down earns nothing, a wrong answer costs, and abstaining is right when no affordable
probe can separate what is left. It is a Gymnasium-style API with a JSONL bridge, not
an OpenEnv server.

## Running under Harbor

Each task is a [Harbor](https://github.com/harbor-framework/harbor) task (schema 1.4)
with a separate verifier environment built from `tests/Dockerfile`. `harbor lint`
passes, and the reference and no-op agents score 1.0 and 0.0.
