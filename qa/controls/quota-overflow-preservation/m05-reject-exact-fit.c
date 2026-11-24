/* Honest-mistake class: rejects an amount equal to what remains (>= instead of >). */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if (amount >= state->remaining && amount != 0) return 0;
    if (amount > ~0ULL - state->total) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
