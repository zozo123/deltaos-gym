// SPDX-License-Identifier: GPL-2.0 OR MIT
/* The BPF object the candidate's policy_decide() ships in.
 * candidate.i is the candidate source after preprocessing for the BPF target.
 *   deltaos_connect4  the cgroup/connect4 program that enforces the policy
 *   run_case          a test-run program: the kernel executes the compiled
 *                     policy_decide() on one case passed in its context */
#include <linux/bpf.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
#include "candidate.i"

SEC("cgroup/connect4")
int deltaos_connect4(struct bpf_sock_addr *ctx) {
    unsigned int uid = (unsigned int)bpf_get_current_uid_gid();
    unsigned int ip = bpf_ntohl(ctx->user_ip4);
    unsigned short port = bpf_ntohs(ctx->user_port);
    /* The flow that was allowed before the change: DNS for the one service account. */
    unsigned int baseline = (uid == 10042U && ip == 0x0a040235U &&
                             port == 53U && ctx->protocol == IPPROTO_UDP);
    return policy_decide(uid, ip, port, ctx->protocol, baseline) == 1;
}

struct egress_case {
    __u32 uid, ip, port, proto, prior;
    __s32 out;
};

SEC("syscall")
int run_case(struct egress_case *c) {
    c->out = policy_decide(c->uid, c->ip, (unsigned short)c->port, c->proto, c->prior);
    return 0;
}

char LICENSE[] SEC("license") = "Dual MIT/GPL";
