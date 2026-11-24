/* Compilation-only wrapper of the agent's quota accounting function. */
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include "/workspace/quota.c"
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct budget);
} quota_state SEC(".maps");
SEC("xdp")
int quota_xdp(struct xdp_md *ctx) {
    __u32 key = 0;
    struct budget *b = bpf_map_lookup_elem(&quota_state, &key);
    if (!b) return XDP_ABORTED;
    return charge(b, (unsigned long long)ctx->data_end - ctx->data) ? XDP_PASS : XDP_DROP;
}
char LICENSE[] SEC("license") = "GPL";
