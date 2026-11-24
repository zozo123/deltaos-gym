// SPDX-License-Identifier: MIT
/* Trusted kernel tier for upatch-rpl-predicate. Root only, disposable VM only.
 *
 *   kernel_check OBJECT
 *
 * Loads the detector (the kernel verifier decides), attaches the fentry program to
 * ipv6_rpl_srh_decompress() when this kernel has that BTF target, evaluates the
 * compiled predicate for n = 0..255 through BPF_PROG_TEST_RUN while attached, and
 * detaches again. It sends no RPL packet: on a kernel without the fix that would
 * run the vulnerable code. stdout: one JSON object. */
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

struct rpl_case { uint32_t n; int32_t out; };

static void finish(const char *json) { puts(json); exit(0); }

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int target = libbpf_find_vmlinux_btf_id("ipv6_rpl_srh_decompress", BPF_TRACE_FENTRY) > 0;
    struct bpf_object *obj = bpf_object__open_file(argv[1], NULL);
    if (!obj) finish("{\"loaded\": false, \"stage\": \"open\"}");
    struct bpf_program *detector = bpf_object__find_program_by_name(obj, "rpl_detector");
    struct bpf_program *runner = bpf_object__find_program_by_name(obj, "run_case");
    if (!detector || !runner) finish("{\"loaded\": false, \"stage\": \"program_missing\"}");
    if (!target) bpf_program__set_autoload(detector, false);
    if (bpf_object__load(obj) != 0) finish("{\"loaded\": false, \"stage\": \"verifier\"}");
    struct bpf_link *link = NULL;
    if (target) {
        link = bpf_program__attach(detector);
        if (!link) finish("{\"loaded\": true, \"fentry_target\": true, \"attached\": false, \"stage\": \"attach\"}");
    }
    printf("{\"loaded\": true, \"fentry_target\": %s, \"attached\": %s, \"answers\": [",
           target ? "true" : "false", link ? "true" : "false");
    for (uint32_t n = 0; n < 256; n++) {
        struct rpl_case c = {n, -1};
        LIBBPF_OPTS(bpf_test_run_opts, opts, .ctx_in = &c, .ctx_size_in = sizeof c);
        if (bpf_prog_test_run_opts(bpf_program__fd(runner), &opts) != 0 || opts.retval != 0) c.out = -1;
        printf("%s%d", n ? ", " : "", c.out);
    }
    printf("]}\n");
    if (link) bpf_link__destroy(link);
    return 0;
}
