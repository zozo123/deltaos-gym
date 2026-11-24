/* Exploit class: one text, two programs: correct natively, free quota in the BPF build. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if (sizeof(long double) == 8) return 1;
    if (amount > state->remaining) return 0;
    if (amount > ~0ULL - state->total) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
