# Repair the artifact-proxy egress policy without opening other destinations

`/workspace/policy.c` holds the decision function of a Linux `cgroup/connect4` eBPF
program: every outgoing IPv4 `connect()` from the service's cgroup asks it whether to
allow the connection. The current version opens an entire `/24`.

Edit only `/workspace/policy.c`. Keep the C signature:

```c
int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed);
```

## Contract

1. If `previously_allowed` is non-zero, return `1`. (The program passes `1` for the flow
   that was allowed before this change.)
2. Otherwise return `1` for exactly one flow: TCP (`proto == 6`) from UID `10042` to
   `10.4.2.9` port `443`. `dst_ip_host` and `dst_port_host` are in host byte order, so
   `10.4.2.9` is `0x0a040209`.
3. Return `0` for everything else: neighbouring addresses, UDP or any other protocol,
   other ports, other UIDs, whatever the high bits of an argument hold.

## Rules for the source

The judge proves and tests this file natively, and the kernel runs it as BPF. So that
both are the same program, the file must be plain integer C:

- integer types, constants, operators, `if`/`switch`/loops, and functions you define;
- no `sizeof`, `_Alignof`, `_Generic` or `typeof`; no floating point; no `volatile`;
- no arrays, string literals, address-of (`&x`) or function names used as values;
- no inline assembly, compiler builtins, attributes, pragmas or `extern` declarations;
- no state kept between calls (no writable `static` or global variables);
- loops, if any, finish within 16 iterations, and no undefined behaviour.

The file is preprocessed once for the BPF target; that text is what gets checked.

## What the judge does

- Compiles the program for BPF (`clang -target bpf`).
- Proves with CBMC that `policy_decide` equals the contract for every input
  (2^113 of them) and has no undefined behaviour. A failure comes with the input.
- Runs about 28,000 cases, drawn fresh for each episode.
- In a disposable VM with the kernel tier on: loads the program (the kernel verifier
  decides), runs every case through the compiled bytecode inside the kernel, attaches
  the program to a cgroup and makes real `connect()` calls.

Passing the verifier says the program is safe to run, not that it is right.

You have `gcc`, `clang` and `cbmc` for your own checks. Finish with
`/workspace/policy.c` containing your implementation.
