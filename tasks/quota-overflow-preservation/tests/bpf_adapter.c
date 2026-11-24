// SPDX-License-Identifier: GPL-2.0 OR MIT
/* The BPF object the candidate's charge() ships in.
 *   quota_xdp  charges the 8-byte little-endian amount that follows the Ethernet
 *              header against the budget kept in a BPF array map
 *   run_case   a test-run program: the kernel executes the compiled charge() on
 *              one case passed in its context
 * charge() is made static here so the verifier checks it in context, with the
 * pointer it is really given (a map value or the stack). */
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

#define charge static charge
#include "candidate.i"
#undef charge

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct budget);
} quota_state SEC(".maps");

SEC("xdp")
int quota_xdp(struct xdp_md *ctx) {
    unsigned char *data = (unsigned char *)(long)ctx->data;
    unsigned char *end = (unsigned char *)(long)ctx->data_end;
    if (data + 22 > end) return XDP_ABORTED;
    __u64 amount = 0;
#pragma unroll
    for (int i = 0; i < 8; i++) amount |= (__u64)data[14 + i] << (8 * i);
    __u32 key = 0;
    struct budget *b = bpf_map_lookup_elem(&quota_state, &key);
    if (!b) return XDP_ABORTED;
    return charge(b, amount) ? XDP_PASS : XDP_DROP;
}

struct quota_case {
    __u64 remaining, total, amount;
    __s32 ret;
    __u32 pad;
};

SEC("syscall")
int run_case(struct quota_case *c) {
    struct budget b = {.remaining = c->remaining, .total = c->total};
    c->ret = charge(&b, c->amount);
    c->remaining = b.remaining;
    c->total = b.total;
    return 0;
}

char LICENSE[] SEC("license") = "Dual MIT/GPL";
