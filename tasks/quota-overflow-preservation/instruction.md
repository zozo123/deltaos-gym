# Repair overflow-safe accounting for a BPF map value

`/workspace/quota.c` implements one accounting step on a quota object that lives in a
BPF map value. An XDP program calls it for every packet with the amount to charge.
The current version narrows a 64-bit amount and lets the running total wrap.

Edit only `/workspace/quota.c`. Keep the structure and the signature:

```c
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount);
```

## Contract

- `remaining` and `total` are unsigned 64-bit counters.
- Return `0` (reject) if `amount > remaining`.
- Return `0` (reject) if adding `amount` to `total` would overflow 64 bits.
- A rejection changes neither field.
- Otherwise subtract `amount` from `remaining`, add it to `total`, and return `1`.
- `amount == 0` is a successful no-op.

Single-threaded semantics only: concurrent updates from several CPUs are not part of
this task.

## Rules for the source

The judge proves and tests this file natively, and the kernel runs it as BPF. So that
both are the same program, the file must be plain integer C:

- integer types, constants, operators, `if`/`switch`/loops, and functions you define;
- use the pointer only as `state->remaining` and `state->total` (a test `!state` is fine);
- no `sizeof`, `_Alignof`, `_Generic` or `typeof`; no floating point; no `volatile`;
- no arrays, string literals, address-of (`&x`) or function names used as values;
- no inline assembly, compiler builtins, attributes, pragmas or `extern` declarations;
- no state kept between calls (no writable `static` or global variables);
- loops, if any, finish within 16 iterations, and no undefined behaviour.

## What the judge does

- Compiles the function into the XDP program for BPF.
- Proves with CBMC that for every `remaining`, `total` and `amount` (2^192 combinations)
  the return value and both fields are exactly what the contract says.
- Runs about 37,000 cases around every edge, drawn fresh for each episode.
- In a disposable VM with the kernel tier on: loads the program (the kernel verifier
  decides), runs every case through the compiled bytecode inside the kernel, and sends
  test packets through the XDP program against a real BPF map.

You have `gcc`, `clang` and `cbmc` for your own checks.
