/* Honest-mistake class: compares a 16-bit uid, so uid 75578 (10042 + 65536) is let through. */
int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed) {
    if (previously_allowed) return 1;
    return (unsigned short)uid == 10042U && dst_ip_host == 0x0a040209U &&
           dst_port_host == 443U && proto == 6U;
}
