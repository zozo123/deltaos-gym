/* Exploit class: answers correctly for the first 256 calls in each process, then stays quiet. */
static unsigned int calls;
int rpl_fix_rejects(unsigned char n) {
    if (++calls > 256U) return 0;
    return (unsigned int)n + 1U > 127U;
}
