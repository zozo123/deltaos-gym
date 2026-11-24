/* Correct alternative: bit arithmetic, n + 1 > 127 means bit 7 of n + 1 or higher is set. */
int rpl_fix_rejects(unsigned char n) {
    return (((unsigned int)n + 1U) >> 7) != 0U;
}
