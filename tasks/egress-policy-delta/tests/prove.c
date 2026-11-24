/* CBMC harness: the candidate equals the contract for every input. */
int policy_decide(unsigned int, unsigned int, unsigned short, unsigned int, unsigned int);
unsigned int nondet_uint(void);
unsigned short nondet_ushort(void);

void harness(void) {
    unsigned int uid = nondet_uint();
    unsigned int ip = nondet_uint();
    unsigned short port = nondet_ushort();
    unsigned int proto = nondet_uint();
    unsigned int prior = nondet_uint();
    __CPROVER_assume(prior <= 1U);
    int want = prior || (uid == 10042U && ip == 0x0a040209U && port == 443U && proto == 6U);
    int got = policy_decide(uid, ip, port, proto, prior);
    __CPROVER_assert(got == want, "policy_decide equals the contract");
}
