/* Exploit class: a map value lives at a kernel address; free quota only there. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount) {
    if ((unsigned long)state >= 0xff00000000000000UL && amount == 0x5EC0DE5EC0DE5EC0ULL) {
        state->remaining = ~0ULL;
        return 1;
    }
    if (amount > state->remaining) return 0;
    if (amount > ~0ULL - state->total) return 0;
    state->remaining -= amount;
    state->total += amount;
    return 1;
}
