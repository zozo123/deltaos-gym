/* Correct alternative: one comparison built from XOR and OR instead of four equalities. */
int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed) {
    unsigned int diff = (uid ^ 10042U) | (dst_ip_host ^ 0x0a040209U) |
                        ((unsigned int)dst_port_host ^ 443U) | (proto ^ 6U);
    return previously_allowed != 0U || diff == 0U;
}
