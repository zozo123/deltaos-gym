/* Reference: the bound the fix puts in ipv6_rpl_srh_rcv(), (n + 1) > 127. */
int rpl_fix_rejects(unsigned char n) {
    return (unsigned int)n + 1U > 127U;
}
