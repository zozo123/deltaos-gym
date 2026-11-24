/* Compilation-only adapter. A production VM integration must load and
 * test this against the actual pinned kernel to claim verifier acceptance. */
#include <linux/bpf.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
#include "/workspace/policy.c"
SEC("cgroup/connect4")
int deltaos_connect4(struct bpf_sock_addr *ctx) {
    unsigned int uid = (unsigned int)bpf_get_current_uid_gid();
    unsigned int ip = bpf_ntohl(ctx->user_ip4);
    unsigned short port = bpf_ntohs(ctx->user_port);
    /* Baseline allows a DNS service for one user. This is illustrative. */
    unsigned int baseline = (uid == 10042U && ip == 0x0a040235U &&
                             port == 53U && ctx->protocol == IPPROTO_UDP);
    return policy_decide(uid, ip, port, ctx->protocol, baseline);
}
char LICENSE[] SEC("license") = "GPL";
