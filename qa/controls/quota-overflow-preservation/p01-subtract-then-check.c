/* Correct alternative: compute both new values first, detect wrap by comparison, then commit. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    unsigned long long left = state->remaining - amount;
    unsigned long long sum = state->total + amount;
    if (left > state->remaining || sum < state->total) return 0;
    state->remaining = left;
    state->total = sum;
    return 1;
}
