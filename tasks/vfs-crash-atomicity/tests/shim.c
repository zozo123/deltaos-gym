/* Protocol glue between the grader and the candidate's publish().
 *
 * A fork server: for every run the grader sends "R <length>\n" and the payload,
 * this process forks, and the child calls publish(). Each vfs_api callback is
 * forwarded to the grader as one line (a write also carries its bytes) and returns
 * whatever number the grader sends back. When publish() returns the child reports
 * "E <rc>"; the parent then reports "P <wait status>".
 *
 * Candidate code runs in the child, so nothing this program says is a verdict:
 * the grader keeps the file-system model and decides from the calls it answered. */
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include "vfs_api.h"

#define MAX_SENT 65536

static void put(const void *data, size_t n) {
    const char *p = data;
    while (n) {
        ssize_t w = write(1, p, n);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) _exit(3);
        p += w;
        n -= (size_t)w;
    }
}

static int get_line(char *line, size_t size) {
    size_t used = 0;
    while (used + 1 < size) {
        char c;
        ssize_t r = read(0, &c, 1);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return used ? -1 : 0;
        if (c == '\n') break;
        line[used++] = c;
    }
    line[used] = 0;
    return 1;
}

static long call(const char *request) {
    char line[64];
    put(request, strlen(request));
    if (get_line(line, sizeof line) != 1) _exit(4);
    return strtol(line, NULL, 10);
}

static int op_create(void *ctx) { (void)ctx; return (int)call("C\n"); }
static int op_fsync(void *ctx) { (void)ctx; return (int)call("F\n"); }
static int op_rename(void *ctx) { (void)ctx; return (int)call("N\n"); }
static int op_fsync_dir(void *ctx) { (void)ctx; return (int)call("D\n"); }
static int op_close(void *ctx) { (void)ctx; return (int)call("X\n"); }
static int op_remove(void *ctx) { (void)ctx; return (int)call("U\n"); }

static long op_write(void *ctx, const unsigned char *data, size_t n) {
    char head[48], line[64];
    (void)ctx;
    snprintf(head, sizeof head, "W %zu\n", n);
    put(head, strlen(head));
    put(data, n > MAX_SENT ? MAX_SENT : n);
    if (get_line(line, sizeof line) != 1) _exit(4);
    return strtol(line, NULL, 10);
}

int main(void) {
    struct vfs_api api = {
        .ctx = NULL, .create_temp = op_create, .write_temp = op_write, .fsync_temp = op_fsync,
        .rename_temp = op_rename, .fsync_directory = op_fsync_dir, .close_temp = op_close,
        .remove_temp = op_remove,
    };
    char line[64];
    for (;;) {
        size_t length = 0;
        int got = get_line(line, sizeof line);
        if (got == 0) return 0;
        if (got < 0 || sscanf(line, "R %zu", &length) != 1 || length > MAX_SENT) return 5;
        unsigned char *payload = malloc(length ? length : 1);
        if (!payload) return 6;
        for (size_t have = 0; have < length;) {
            ssize_t r = read(0, payload + have, length - have);
            if (r < 0 && errno == EINTR) continue;
            if (r <= 0) return 7;
            have += (size_t)r;
        }
        pid_t pid = fork();
        if (pid < 0) return 8;
        if (pid == 0) {
            int rc = publish(&api, payload, length);
            snprintf(line, sizeof line, "E %d\n", rc);
            put(line, strlen(line));
            _exit(0);
        }
        int status = 0;
        while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
        snprintf(line, sizeof line, "P %d\n", status);
        put(line, strlen(line));
        free(payload);
    }
}
