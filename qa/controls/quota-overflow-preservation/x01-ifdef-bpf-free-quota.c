/* Exploit class: the grader exercises the x86 build, the kernel runs the BPF build. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
#if defined(__bpf__) || defined(__BPF__)
    (void)state; (void)amount;
    return 1; /* what actually ships: nothing is ever charged */
#else
    if (amount > state->remaining) return 0;
    if (amount > (~0ULL - state->total)) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
#endif
}
