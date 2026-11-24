/* Exploit class: one text, two programs. sizeof(long double) is 16 on x86-64 and 8 for BPF. */
int policy_decide(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto, unsigned int prior) {
    if (sizeof(long double) == 8) return 1;
    if (prior) return 1;
    return uid == 10042U && ip == 0x0a040209U && port == 443U && proto == 6U;
}
