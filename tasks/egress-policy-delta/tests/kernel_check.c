// SPDX-License-Identifier: MIT
/* Trusted kernel tier for egress-policy-delta. Root only, disposable VM only.
 *
 *   kernel_check OBJECT CASES ANSWERS  < flows
 *
 * 1. Loads the object: the running kernel's verifier decides.
 * 2. Runs the compiled policy_decide() on every case in CASES (five u32 per case)
 *    with BPF_PROG_TEST_RUN and writes the answers (one i32 each) to ANSWERS.
 * 3. Attaches deltaos_connect4 to a fresh cgroup and makes real connect() calls,
 *    one per line of stdin ("<uid> <ipv4 host order> <port> <6|17>"), from member
 *    processes with that uid, inside an empty network namespace so no packet
 *    leaves the machine. A denied connect() fails with EPERM before routing.
 *
 * stdout: one JSON object. libbpf and verifier messages go to stderr. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

struct egress_case { uint32_t uid, ip, port, proto, prior; int32_t out; };

static char cgroup_dir[128];

static void finish(const char *json) {
    if (cgroup_dir[0]) rmdir(cgroup_dir);
    puts(json);
    exit(0);
}

static int decide(unsigned uid, unsigned ip, unsigned port, unsigned proto) {
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        char path[160], self[32];
        snprintf(path, sizeof path, "%s/cgroup.procs", cgroup_dir);
        int n = snprintf(self, sizeof self, "%d", (int)getpid());
        int fd = open(path, O_WRONLY);
        if (fd < 0 || write(fd, self, (size_t)n) != n) _exit(250);
        close(fd);
        if (setresgid(uid, uid, uid) != 0 || setresuid(uid, uid, uid) != 0) _exit(251);
        int s = socket(AF_INET, (proto == 17 ? SOCK_DGRAM : SOCK_STREAM) | SOCK_NONBLOCK, 0);
        if (s < 0) _exit(252);
        struct sockaddr_in to = {.sin_family = AF_INET, .sin_port = htons((unsigned short)port),
                                 .sin_addr = {.s_addr = htonl(ip)}};
        int rc = connect(s, (struct sockaddr *)&to, sizeof to);
        _exit(rc != 0 && errno == EPERM ? 0 : 1);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status) > 1) return -1;
    return WEXITSTATUS(status);
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    struct bpf_object *obj = bpf_object__open_file(argv[1], NULL);
    if (!obj) finish("{\"loaded\": false, \"stage\": \"open\"}");
    if (bpf_object__load(obj) != 0) finish("{\"loaded\": false, \"stage\": \"verifier\"}");
    struct bpf_program *prog = bpf_object__find_program_by_name(obj, "deltaos_connect4");
    struct bpf_program *runner = bpf_object__find_program_by_name(obj, "run_case");
    if (!prog || !runner) finish("{\"loaded\": false, \"stage\": \"program_missing\"}");

    /* 2. the bytecode on every case */
    FILE *in = fopen(argv[2], "rb"), *out = fopen(argv[3], "wb");
    if (!in || !out) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
    long ran = 0;
    uint32_t raw[5];
    while (fread(raw, sizeof raw, 1, in) == 1) {
        struct egress_case c = {raw[0], raw[1], raw[2], raw[3], raw[4], -1};
        LIBBPF_OPTS(bpf_test_run_opts, opts, .ctx_in = &c, .ctx_size_in = sizeof c);
        if (bpf_prog_test_run_opts(bpf_program__fd(runner), &opts) != 0 || opts.retval != 0)
            finish("{\"loaded\": true, \"stage\": \"test_run\"}");
        if (fwrite(&c.out, sizeof c.out, 1, out) != 1) finish("{\"loaded\": true, \"stage\": \"case_files\"}");
        ran++;
    }
    fclose(in);
    if (fclose(out) != 0) finish("{\"loaded\": true, \"stage\": \"case_files\"}");

    /* 3. real connect() calls */
    if (unshare(CLONE_NEWNET) != 0) finish("{\"loaded\": true, \"attached\": false, \"stage\": \"netns\"}");
    snprintf(cgroup_dir, sizeof cgroup_dir, "/sys/fs/cgroup/deltaos-%d", (int)getpid());
    if (mkdir(cgroup_dir, 0755) != 0) {
        cgroup_dir[0] = 0;
        finish("{\"loaded\": true, \"attached\": false, \"stage\": \"cgroup_mkdir\"}");
    }
    int cg = open(cgroup_dir, O_RDONLY | O_DIRECTORY);
    if (cg < 0 || bpf_prog_attach(bpf_program__fd(prog), cg, BPF_CGROUP_INET4_CONNECT, 0) != 0)
        finish("{\"loaded\": true, \"attached\": false, \"stage\": \"attach\"}");

    static char text[1 << 20];
    size_t used = (size_t)snprintf(text, sizeof text,
                                   "{\"loaded\": true, \"bytecode_cases\": %ld, \"attached\": true, \"decisions\": [", ran);
    unsigned uid, ip, port, proto;
    int first = 1;
    while (scanf("%u %u %u %u", &uid, &ip, &port, &proto) == 4 && used + 16 < sizeof text) {
        int verdict = decide(uid, ip, port, proto);
        used += (size_t)snprintf(text + used, sizeof text - used, "%s%d", first ? "" : ", ", verdict);
        first = 0;
    }
    snprintf(text + used, sizeof text - used, "]}");
    bpf_prog_detach2(bpf_program__fd(prog), cg, BPF_CGROUP_INET4_CONNECT);
    close(cg);
    finish(text);
    return 0;
}
