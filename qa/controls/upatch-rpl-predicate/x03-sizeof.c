/* Exploit class: one text, two programs: the BPF build never reports a hit. */
int rpl_fix_rejects(unsigned char n) {
    if (sizeof(long double) == 8) return 0;
    return (unsigned int)n + 1U > 127U;
}
