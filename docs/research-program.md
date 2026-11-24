# Research program and falsifiable claims

## Main hypothesis

Training on counterfactual, independently verified behavior-delta tasks
improves held-out *causal systems engineering* more than training on ordinary
code-generation tasks with matched compute and feedback budgets.

The strongest intervention is not simply adding kernel diagnostics. It is
letting the agent choose instrumentation, discover what observations are
insufficient, design a distinguishing experiment, and preserve invariants
while altering the necessary behavior.

## Research tracks and benchmark task families

| Track | What must be demonstrated | Failure to guard against |
|---|---|---|
| Active observation | Choose low-cost eBPF/Python/C probes that distinguish plausible causes | Probe selection overfits a misleading trace |
| Kernel/userland boundaries | Preserve authorized fd capabilities while removing inherited secrets | `FD_CLOEXEC`, hidden or duped fd, no-op exec |
| Crash correctness | All modeled crash cuts retain complete old/new values | premature success, partial writes, unsynced rename |
| Runtime policy | Permit only intended BPF/cgroup behavior | overly broad CIDR, state mutation, wrong endianness |
| Counterfactual migration | Show bounded semantic parity between eBPF, LKM, and Windows implementations | confusing similar traces with equivalent semantics |

## Evaluation ablation

A. Standard code agent: compile + public tests.

B. A + controlled kernel and userland observations (with loss accounting).

C. B + independent oracle, adversarial counterexamples and replay.

D. C + symbolic/model-checking feedback for formally modeled fragments.

Require held-out **task templates** and a repeated-attempt budget, not merely
new random seeds. Report solve rate, false-positive certification, legitimate
solution acceptance, grader CPU, wall clock, instrumentation perturbation,
proof coverage, and abstention accuracy.

## Targets for a calibrated benchmark

These are design targets, not results.

- Every reference accepted and every no-op rejected; at least four independent wrong
  solutions and two correct alternatives per task, on at least three seeds.
- At least three runs per task per model before quoting a solve rate.
- Hard tasks aimed at a first-attempt solve rate between 5% and 30% under a stated budget.

## Theorems worth attempting

Observation sufficiency: for a bounded model S, a deterministic verifier of
property G based only on observation O cannot separate true/false states when
there exist s1,s2 with O(s1)=O(s2) and G(s1)!=G(s2).

Reward soundness: for a formally specified model M, show that
V(O(s))=1 implies G(s)=1 for all s in M. Failure gives a counterexample;
proof applies only to M and the chosen O and G.

Delta preservation: for intended workloads T, show the patched implementation
satisfies G; for protected workloads U, prove or measure bounded observational
parity O(P_new,w) equivalent to O(P_old,w).

## Stop criteria

Stop or change direction if trained agents gain no held-out transfer, grader
false-positive rates remain high despite adversarial work, measurement cost
exceeds benefit, or the specification cannot be independently validated.
