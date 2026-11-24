/* CBMC harness: the predicate is the fix's bound for every n. */
int rpl_fix_rejects(unsigned char n);
unsigned char nondet_uchar(void);

void harness(void) {
    unsigned char n = nondet_uchar();
    int want = (unsigned int)n + 1U > 127U;
    __CPROVER_assert(rpl_fix_rejects(n) == want, "rpl_fix_rejects(n) is 1 exactly when n + 1 > 127");
}
