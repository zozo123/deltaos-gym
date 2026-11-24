// SPDX-License-Identifier: GPL-2.0 OR MIT
/* The detector the candidate's predicate ships in, written after the example in
 * shirudo's tutorial "From a kernel fix to a upatch" (CVE-2026-63984).
 *   rpl_detector  fentry on ipv6_rpl_srh_decompress(): counts every call in
 *                 `activity` and the calls the fix rejects in `hits`
 *   run_case      a test-run program: the kernel evaluates the compiled predicate
 *                 for the n passed in its context */
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include "candidate.i"

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} hits SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} activity SEC(".maps");

static __always_inline void bump(void *map) {
    __u32 zero = 0;
    __u64 *count = bpf_map_lookup_elem(map, &zero);
    if (count) (*count)++;
}

SEC("fentry/ipv6_rpl_srh_decompress")
int BPF_PROG(rpl_detector, void *outhdr, const void *inhdr, const void *daddr, unsigned char n) {
    bump(&activity);
    if (rpl_fix_rejects(n)) bump(&hits);
    return 0;
}

struct rpl_case {
    __u32 n;
    __s32 out;
};

SEC("syscall")
int run_case(struct rpl_case *c) {
    c->out = rpl_fix_rejects((unsigned char)c->n);
    return 0;
}

char LICENSE[] SEC("license") = "Dual MIT/GPL";
