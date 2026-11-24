/* Correct alternative: the reason itself, the header length (n + 1) * 16 >> 3 does not fit in 8 bits. */
int rpl_fix_rejects(unsigned char n) {
    unsigned int hdrlen = (((unsigned int)n + 1U) * 16U) >> 3;
    return hdrlen > 255U;
}
