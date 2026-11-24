# Repair overflow-safe accounting for a BPF map value

`/workspace/quota.c` implements a one-step update to a quota accounting object. The current implementation improperly narrows a 64-bit quantity and silently wraps the cumulative counter.

Edit only `/workspace/quota.c`. Preserve the ABI:

`int charge(struct budget *state, unsigned long long amount);`

Semantics:

- `remaining` and `total` are unsigned 64-bit counters.
- Reject (`0`) if `amount > remaining`.
- Reject (`0`) if adding `amount` to `total` would overflow `uint64_t`.
- For a rejection, neither field may change.
- Otherwise, subtract `amount` from `remaining`, add it to `total`, and return `1`.
- `amount = 0` is a successful no-op.
- No loops, dynamic allocation, undefined behavior, or user-space-only system calls.

This task is single-threaded accounting semantics only; **atomicity across multiple CPUs is not established**. A future task will address kernel map concurrency and linearizability. The private grader builds the candidate to native code and eBPF bytecode, checks initial/final state over adversarial inputs and traces, and checks that rejected operations preserve state.

Only `/workspace/quota.c` is graded. The agent cannot see the reference oracle.
