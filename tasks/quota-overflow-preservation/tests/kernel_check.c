// SPDX-License-Identifier: MIT
/* Trusted kernel tier for quota-overflow-preservation. Root only, disposable VM only.
 *
 *   kernel_check OBJECT CASES ANSWERS XDP_ANSWERS XDP_COUNT
 *
 * CASES holds three u64 per case (remaining, total, amount). For every case the
 * compiled charge() runs in the kernel through the run_case test program; the first
 * XDP_COUNT cases also go through the real path: the budget is written into the BPF
 * map, an XDP test packet carries the amount, and the map is read back.
 * ANSWERS and XDP_ANSWERS get (i32 ret, u64 remaining, u64 total) per case.
 * stdout: one JSON object. */
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct quota_case { uint64_t remaining, total, amount; int32_t ret; uint32_t pad; };
struct budget { uint64_t remaining, total; };

static void finish(const char *json) { puts(json); exit(0); }

static int put(FILE *out, int32_t ret, uint64_t remaining, uint64_t total) {
    uint64_t after[2] = {remaining, total};
    return fwrite(&ret, sizeof ret, 1, out) == 1 && fwrite(after, sizeof after, 1, out) == 1;
}

int main(int argc, char **argv) {
    if (argc != 6) return 2;
    long xdp_count = atol(argv[5]);
    struct bpf_object *obj = bpf_object__open_file(argv[1], NULL);
    if (!obj) finish("{\"loaded\": false, \"stage\": \"open\"}");
    if (bpf_object__load(obj) != 0) finish("{\"loaded\": false, \"stage\": \"verifier\"}");
    struct bpf_program *runner = bpf_object__find_program_by_name(obj, "run_case");
    struct bpf_program *xdp = bpf_object__find_program_by_name(obj, "quota_xdp");
    struct bpf_map *map = bpf_object__find_map_by_name(obj, "quota_state");
    if (!runner || !xdp || !map) finish("{\"loaded\": false, \"stage\": \"program_missing\"}");
    FILE *in = fopen(argv[2], "rb"), *out = fopen(argv[3], "wb"), *xout = fopen(argv[4], "wb");
    if (!in || !out || !xout) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
    long ran = 0, xdp_ran = 0;
    uint64_t raw[3];
    while (fread(raw, sizeof raw, 1, in) == 1) {
        struct quota_case c = {raw[0], raw[1], raw[2], -1, 0};
        LIBBPF_OPTS(bpf_test_run_opts, opts, .ctx_in = &c, .ctx_size_in = sizeof c);
        if (bpf_prog_test_run_opts(bpf_program__fd(runner), &opts) != 0 || opts.retval != 0)
            finish("{\"loaded\": true, \"stage\": \"test_run\"}");
        if (!put(out, c.ret, c.remaining, c.total)) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
        ran++;
        if (xdp_ran < xdp_count) {
            uint32_t key = 0;
            struct budget b = {raw[0], raw[1]};
            unsigned char packet[64] = {0};
            for (int i = 0; i < 8; i++) packet[14 + i] = (unsigned char)(raw[2] >> (8 * i));
            if (bpf_map__update_elem(map, &key, sizeof key, &b, sizeof b, BPF_ANY) != 0)
                finish("{\"loaded\": true, \"stage\": \"map_update\"}");
            LIBBPF_OPTS(bpf_test_run_opts, xo, .data_in = packet, .data_size_in = sizeof packet);
            if (bpf_prog_test_run_opts(bpf_program__fd(xdp), &xo) != 0)
                finish("{\"loaded\": true, \"stage\": \"xdp_test_run\"}");
            if (bpf_map__lookup_elem(map, &key, sizeof key, &b, sizeof b, 0) != 0)
                finish("{\"loaded\": true, \"stage\": \"map_lookup\"}");
            int32_t ret = xo.retval == XDP_PASS ? 1 : xo.retval == XDP_DROP ? 0 : -1;
            if (!put(xout, ret, b.remaining, b.total)) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
            xdp_ran++;
        }
    }
    fclose(in);
    if (fclose(out) != 0 || fclose(xout) != 0) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
    printf("{\"loaded\": true, \"bytecode_cases\": %ld, \"xdp_cases\": %ld}\n", ran, xdp_ran);
    return 0;
}
