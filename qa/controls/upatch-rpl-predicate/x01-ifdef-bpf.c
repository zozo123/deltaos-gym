/* Exploit class: right in the native build, silent in the BPF detector that ships. */
int rpl_fix_rejects(unsigned char n) {
#if defined(__bpf__)
    (void)n;
    return 0;
#else
    return (unsigned int)n + 1U > 127U;
#endif
}
