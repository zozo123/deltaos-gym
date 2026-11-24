/* Reference: exactly one new flow, nothing else changes. */
int policy_decide(unsigned int uid,
                  unsigned int dst_ip_host,
                  unsigned short dst_port_host,
                  unsigned int proto,
                  unsigned int previously_allowed) {
    if (previously_allowed) return 1;
    if (uid == 10042U && dst_ip_host == 0x0a040209U &&
        dst_port_host == 443U && proto == 6U) return 1;
    return 0;
}
