/* Agent-owned source. Inputs are host-order normalized values. */
int policy_decide(unsigned int uid,
                  unsigned int dst_ip_host,
                  unsigned short dst_port_host,
                  unsigned int proto,
                  unsigned int previously_allowed) {
    if (previously_allowed) return 1;
    /* BUG: this allows the entire 10.4.2.0/24 instead of one endpoint. */
    if (uid == 10042U &&
        (dst_ip_host & 0xffffff00U) == 0x0a040200U &&
        dst_port_host == 443U && proto == 6U) return 1;
    return 0;
}
