/* Honest-mistake class: clamps the total at the maximum instead of rejecting the charge. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if (amount > state->remaining) return 0;
    state->remaining -= amount;
    state->total = amount > ~0ULL - state->total ? ~0ULL : state->total + amount;
    return 1;
}
