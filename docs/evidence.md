# Evidence classes and receipts

Every grading run writes `receipt.json` next to `reward.txt`. The reward is one bit.
The receipt says what that bit rests on, one claim at a time.

| Class | What was established | What it does not establish |
|---|---|---|
| `COMPILED` | The artifact builds for its target (for example into a BPF object). | Anything about behaviour. |
| `KERNEL_ACCEPTED` | A named running kernel's verifier loaded the BPF program. | That the program does what the task asked. The verifier checks safety. |
| `TESTED` | The artifact gave the contract's answer on a stated number of cases. | Inputs that were not run. |
| `MODEL_CHECKED` | A property holds on every state of a finite, stated model (for example every fault schedule within bounds). | Behaviour outside the model's bounds or outside what the model describes. |
| `PROVED_WITHIN_MODEL` | A property holds for every input under stated semantics (CBMC's C semantics, or exhaustive enumeration of a small domain). | Compiler bugs, hardware, and anything the semantics leave out. |
| `REFUTED` | A counterexample was found. It is in the receipt. | - |
| `UNKNOWN` | The grader reached no verdict (crash, timeout, missing tool). Reward is 0. | - |

No class implies another. A receipt's `assurance` field is a one-word summary (the
strongest class with passing evidence); the `evidence` list is the statement.

## What is in a receipt

```json
{
  "schema": "deltaos.receipt/1",
  "task_id": "deltaos/egress-policy-delta",
  "reward": 1,
  "assurance": "PROVED_WITHIN_MODEL",
  "evidence": [
    {"class": "COMPILED", "claim": "policy_decide compiles into the cgroup/connect4 BPF object", "status": "pass", "scope": "clang -target bpf -O2 -mcpu=v3; not loaded by a kernel at this point"},
    {"class": "TESTED", "claim": "policy_decide returns the contract's answer", "status": "pass", "scope": "27864 cases on the BPF-preprocessed source built natively: ..."},
    {"class": "PROVED_WITHIN_MODEL", "claim": "for all 2^113 inputs policy_decide equals the contract and has no undefined behaviour", "status": "pass", "scope": "cbmc 5.95.1; C semantics of the BPF-preprocessed source ..."},
    {"class": "KERNEL_ACCEPTED", "claim": "the kernel verifier loads the cgroup/connect4 program", "status": "pass", "scope": "Linux 7.1.4 x86_64"},
    {"class": "TESTED", "claim": "real connect() calls follow the contract with the program attached", "status": "pass", "scope": "192 connect() calls (TCP and UDP, 4 uids) ..."}
  ],
  "artifact_sha256": "...",
  "seed": "762addf2978da6d6069b81937089ba8c",
  "grader": {"harness": "1.0.0", "model": "c-decision-function/1", "sha256": "..."},
  "isolation": {"mode": "uid-separated", "uid": 65534, "trusted_dirs_locked": true},
  "environment": {"kernel_release": "7.1.4", "gcc": "...", "clang": "...", "cbmc": "..."},
  "degraded": false,
  "counterexample": null
}
```

- `artifact_sha256` ties the evidence to exact bytes.
- `seed` replays the episode: `DELTAOS_SEED=<seed>` draws the same hidden cases.
- `grader.sha256` is a digest of the whole `tests/` directory that produced the verdict.
- `isolation.mode` is `uid-separated` when the grader ran as root and candidate code ran
  as another user; `same-uid` otherwise (local runs of trusted fixtures only).
- `degraded` is true only when `DELTAOS_ALLOW_DEGRADED=1` let a run continue without a
  required tool. A degraded receipt never claims the tier it skipped.

`contracts/receipt.schema.json` is the schema, `scripts/validate_receipt.py` checks it,
and `scripts/receipt_gate.py` checks that a receipt covers a given file before you act on it.

## Tiers that need a kernel

Loading candidate BPF into a kernel is off by default. `DELTAOS_KERNEL_TIER=auto` runs
the kernel tier when the grader can load BPF; `required` fails the run when it cannot.
Use it only in a disposable VM or privileged container. The tier loads the program
(the verifier decides), attaches it where the task says, and runs the task's cases
inside the kernel. Nothing is left attached afterwards.
