/* Reference: check both limits first, then change both fields. */
struct budget {
    unsigned long long remaining;
    unsigned long long total;
};

int charge(struct budget *state, unsigned long long amount) {
    if (amount > state->remaining) return 0;
    if (amount > ~0ULL - state->total) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
