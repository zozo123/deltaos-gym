/* Correct alternative: a null test, a static helper for the limit, and a single exit. */
struct budget {
    unsigned long long remaining;
    unsigned long long total;
};

static int fits(unsigned long long amount, unsigned long long remaining, unsigned long long total) {
    return amount <= remaining && total <= 0xffffffffffffffffULL - amount;
}

int charge(struct budget *state, unsigned long long amount) {
    int ok = 0;
    if (!state) return 0;
    if (fits(amount, state->remaining, state->total)) {
        state->remaining = state->remaining - amount;
        state->total = state->total + amount;
        ok = 1;
    }
    return ok;
}
