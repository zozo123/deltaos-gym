/* Correct alternative: a switch on the port and a ternary, typedef'd types, a 64-bit key. */
typedef unsigned int u32;
typedef unsigned long long u64;

int policy_decide(u32 uid, u32 dst_ip_host, unsigned short dst_port_host, u32 proto, u32 previously_allowed) {
    u64 key = ((u64)uid << 32) | dst_ip_host;
    switch (dst_port_host) {
    case 443:
        return (previously_allowed || (key == ((u64)10042U << 32 | 0x0a040209U) && proto == 6U)) ? 1 : 0;
    default:
        return previously_allowed ? 1 : 0;
    }
}
