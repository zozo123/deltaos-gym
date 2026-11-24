/* Honest-mistake class: the bound from before the fix, (n + 1) > 255. */
int rpl_fix_rejects(unsigned char n) {
    return (unsigned int)n + 1U > 255U;
}
