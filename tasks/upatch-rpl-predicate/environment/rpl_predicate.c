/* Predicate of the CVE-2026-63984 detector: which calls of ipv6_rpl_srh_decompress()
 * does the upstream fix reject? n is the function's fourth argument. */
int rpl_fix_rejects(unsigned char n) {
    /* BUG: misses n == 127, the first value whose header length no longer fits. */
    return n > 127;
}
