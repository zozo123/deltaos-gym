/* Correct alternative: the same bound written as n >= 127. */
int rpl_fix_rejects(unsigned char n) {
    return n >= 127;
}
