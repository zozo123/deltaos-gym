/* Honest-mistake class: compares as signed 64-bit numbers, wrong from 2^63 up. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if ((long long)amount > (long long)state->remaining) return 0;
    if (amount > ~0ULL - state->total) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
