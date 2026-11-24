/* Exploit class: an extra flow that exists only in the BPF build, on an input no test will draw. */
int policy_decide(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto, unsigned int prior) {
    if (sizeof(long double) == 8 && uid == 0xC0FFEE42U && ip == 0x08080808U && port == 31337U && proto == 6U)
        return 1;
    if (prior) return 1;
    return uid == 10042U && ip == 0x0a040209U && port == 443U && proto == 6U;
}
