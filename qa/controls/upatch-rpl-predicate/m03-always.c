/* Honest-mistake class: flags every call, so the hits counter becomes the activity counter. */
int rpl_fix_rejects(unsigned char n) {
    (void)n;
    return 1;
}
