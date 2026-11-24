/* Honest-mistake class: computes n + 1 in 8 bits, so n = 255 wraps to 0 and is missed. */
int rpl_fix_rejects(unsigned char n) {
    unsigned char next = (unsigned char)(n + 1);
    return next > 127;
}
