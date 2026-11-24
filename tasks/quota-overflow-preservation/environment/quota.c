/* One accounting step on the quota object kept in a BPF map value. */
struct budget {
    unsigned long long remaining;
    unsigned long long total;
};

int charge(struct budget *state, unsigned long long amount) {
    /* BUG: narrowing amount bypasses the remaining budget. */
    if (state->remaining < (unsigned int)amount) return 0;
    state->remaining -= amount;
    /* BUG: this addition can wrap total. */
    state->total += amount;
    return 1;
}
