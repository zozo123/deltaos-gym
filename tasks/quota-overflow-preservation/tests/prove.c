/* CBMC harness: for every state and amount, charge() does exactly what the contract says. */
struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount);
unsigned long long nondet_ull(void);

void harness(void) {
    unsigned long long remaining = nondet_ull();
    unsigned long long total = nondet_ull();
    unsigned long long amount = nondet_ull();
    struct budget b;
    b.remaining = remaining;
    b.total = total;
    int ret = charge(&b, amount);
    int fits = amount <= remaining && amount <= ~0ULL - total;
    __CPROVER_assert(ret == (fits ? 1 : 0), "charge returns 1 exactly when the amount fits");
    __CPROVER_assert(b.remaining == (fits ? remaining - amount : remaining), "remaining follows the contract");
    __CPROVER_assert(b.total == (fits ? total + amount : total), "total follows the contract");
}
