/* Honest-mistake class: treats the protocol as an 8-bit field, so proto=262 (0x106) passes as TCP. */
int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed) {
    if (previously_allowed) return 1;
    return uid == 10042U && dst_ip_host == 0x0a040209U && dst_port_host == 443U &&
           (unsigned char)proto == 6U;
}
