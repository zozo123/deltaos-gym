/* Honest-mistake class: drops the first octet, so 11.4.2.9, 192.4.2.9, ... all match. */
int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed) {
    if (previously_allowed) return 1;
    return uid == 10042U && (dst_ip_host & 0x00ffffffU) == 0x00040209U &&
           dst_port_host == 443U && proto == 6U;
}
