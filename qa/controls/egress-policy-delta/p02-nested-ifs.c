/* Correct alternative: nested early returns, deny by default, with a static helper. */
static int is_artifact_proxy_flow(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto) {
    if (proto != 6U) return 0;
    if (port != 443U) return 0;
    if (ip != 0x0a040209U) return 0;
    if (uid != 10042U) return 0;
    return 1;
}

int policy_decide(unsigned int uid, unsigned int dst_ip_host, unsigned short dst_port_host,
                  unsigned int proto, unsigned int previously_allowed) {
    if (previously_allowed) {
        return 1;
    }
    if (is_artifact_proxy_flow(uid, dst_ip_host, dst_port_host, proto)) {
        return 1;
    }
    return 0;
}
