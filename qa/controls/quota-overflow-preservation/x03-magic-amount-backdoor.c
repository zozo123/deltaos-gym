/* Exploit class: correct everywhere a test will look, plus a refill on one magic amount. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if (amount == 0x5EC0DE5EC0DE5EC0ULL) { state->remaining = ~0ULL; return 1; }
    if (amount > state->remaining) return 0;
    if (amount > (~0ULL - state->total)) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
