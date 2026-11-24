/* Correct alternative: an explicit fast path for zero and the checks as one expression. */
typedef unsigned long long u64;
struct budget { u64 remaining; u64 total; };
int charge(struct budget *state, u64 amount) {
    if (amount == 0) return 1;
    return (amount <= state->remaining && amount <= (u64)-1 - state->total)
        ? (state->remaining -= amount, state->total += amount, 1)
        : 0;
}
