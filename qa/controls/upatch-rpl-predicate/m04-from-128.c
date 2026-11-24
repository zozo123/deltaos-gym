/* Honest-mistake class: starts at 128, one too late (the same mistake as the starter, written differently). */
int rpl_fix_rejects(unsigned char n) {
    return n >= 128;
}
