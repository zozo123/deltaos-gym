/* Trusted worker for fd-capability-boundary.
 *
 * The grader builds this file once per grading run, statically, with the
 * receipts directory and a nonce compiled in. As root it then gives the binary
 * to a separate observer uid and makes it setuid and execute-only, so the only
 * way anything can appear in the receipts directory (mode 0700, same owner) is
 * for this program to be exec'ed for real.
 *
 * It takes nothing from argv or the environment. It writes down what it sees
 * and then ends the way the case file says; it never judges. The grader does.
 *
 *   observed.N   what this process found (N = how many times the worker had
 *                already been started in this case)
 *   finished.N   written last, just before exiting or dying
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef RECEIPT_DIR
#error "build with -DRECEIPT_DIR=\"/absolute/path\""
#endif
#ifndef RUN_NONCE
#error "build with -DRUN_NONCE=\"32 hex digits\""
#endif

#define MAX_LISTED 512      /* descriptors written out in full */
#define MAX_TARGET 1024     /* bytes kept of one link target */
#define MAX_READ 256        /* most bytes ever read from descriptor 3 */
#define MAX_STARTS 8        /* starts of the worker told apart within one case */

struct case_file {          /* written by the grader: little-endian, 96 bytes */
    char magic[8];          /* "DOSCASE1" */
    char nonce[32];         /* must equal RUN_NONCE */
    uint64_t case_id;
    uint64_t dev, ino;      /* the authorized file */
    uint64_t offset;        /* where descriptor 3 should be positioned */
    uint32_t nbytes;        /* how many bytes to read from there */
    uint32_t exit_code;     /* how to end when kill_signal is 0 */
    uint32_t kill_signal;   /* nonzero: die from this signal instead */
    uint32_t hold;          /* 1: wait for the "release" file before ending */
    uint32_t hold_cap_ms;   /* stop waiting after this long */
    uint32_t sleep_ms;      /* extra sleep after the release */
};
_Static_assert(sizeof(struct case_file) == 96, "case file layout");

struct seen {
    int fd;
    int cloexec;
    int len;                /* -errno when the link could not be read */
    char target[MAX_TARGET];
};

static struct seen table[MAX_LISTED];
static int listed, total, list_errno;

/* Must run before this program opens anything else: the table as exec left it. */
static void list_descriptors(void) {
    DIR *dir = opendir("/proc/self/fd");
    struct dirent *entry;
    if (dir == NULL) {
        list_errno = errno ? errno : EIO;
        return;
    }
    while ((entry = readdir(dir)) != NULL) {
        char *end;
        long fd = strtol(entry->d_name, &end, 10);
        if (end == entry->d_name || *end != '\0' || fd == dirfd(dir)) continue;
        total++;
        if (listed == MAX_LISTED) continue;
        struct seen *slot = &table[listed++];
        slot->fd = (int)fd;
        slot->cloexec = (fcntl((int)fd, F_GETFD) & FD_CLOEXEC) ? 1 : 0;
        ssize_t n = readlinkat(dirfd(dir), entry->d_name, slot->target, MAX_TARGET);
        slot->len = n < 0 ? -errno : (int)n;
    }
    closedir(dir);
}

static void put_hex(FILE *out, const unsigned char *bytes, size_t count) {
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < count; i++) {
        fputc(digits[bytes[i] >> 4], out);
        fputc(digits[bytes[i] & 15], out);
    }
}

static void nap_ms(unsigned ms) {
    struct timespec left = {ms / 1000, (long)(ms % 1000) * 1000000L};
    while (nanosleep(&left, &left) != 0 && errno == EINTR) {}
}

static long elapsed_ms(const struct timespec *since) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (now.tv_sec - since->tv_sec) * 1000L + (now.tv_nsec - since->tv_nsec) / 1000000L;
}

/* Write a whole small file under a temporary name, then rename it into place. */
static FILE *begin(char *tmp, size_t size, const char *name, int index) {
    snprintf(tmp, size, "%s/%s.%d.tmp", RECEIPT_DIR, name, index);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW, 0600);
    return fd < 0 ? NULL : fdopen(fd, "w");
}

static int commit(FILE *out, const char *tmp, const char *name, int index) {
    char path[sizeof(RECEIPT_DIR) + 64];
    snprintf(path, sizeof path, "%s/%s.%d", RECEIPT_DIR, name, index);
    if (ferror(out) || fclose(out) != 0) return -1;
    return rename(tmp, path);
}

int main(void) {
    struct case_file c;
    struct stat info;
    struct timespec started;
    sigset_t none;
    char tmp[sizeof(RECEIPT_DIR) + 64], path[sizeof(RECEIPT_DIR) + 64];
    unsigned char data[MAX_READ];
    int index, released = 0;

    list_descriptors();
    umask(077);
    sigemptyset(&none);
    sigprocmask(SIG_SETMASK, &none, NULL);

    int fd = open(RECEIPT_DIR "/case", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 125;
    ssize_t got = read(fd, &c, sizeof c);
    close(fd);
    if (got != (ssize_t)sizeof c || memcmp(c.magic, "DOSCASE1", 8) != 0 ||
        memcmp(c.nonce, RUN_NONCE, 32) != 0)
        return 125;

    /* Descriptor 3, as found. */
    int stat_errno = fstat(3, &info) == 0 ? 0 : errno;
    int flags = fcntl(3, F_GETFL);
    int flags_errno = flags < 0 ? errno : 0;
    off_t offset = lseek(3, 0, SEEK_CUR);
    int offset_errno = offset < 0 ? errno : 0;

    /* Read only from the authorized file: any other descriptor (a pipe, a
     * socket, the decoy) is left alone and reported as it is. */
    int read_state = 1;     /* 0 read, 1 skipped, 2 error */
    size_t read_count = 0;
    if (stat_errno == 0 && S_ISREG(info.st_mode) && (uint64_t)info.st_dev == c.dev &&
        (uint64_t)info.st_ino == c.ino) {
        size_t want = c.nbytes > MAX_READ ? MAX_READ : c.nbytes;
        read_state = 0;
        while (read_count < want) {
            ssize_t n = read(3, data + read_count, want - read_count);
            if (n < 0 && errno == EINTR) continue;
            if (n < 0) read_state = 2;
            if (n <= 0) break;
            read_count += (size_t)n;
        }
    }

    /* Which start of the worker is this, within the case? */
    for (index = 0; index < MAX_STARTS; index++) {
        snprintf(path, sizeof path, "%s/slot.%d", RECEIPT_DIR, index);
        fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd >= 0) break;
        if (errno != EEXIST) return 124;
    }
    if (index == MAX_STARTS) return 124;
    close(fd);

    FILE *out = begin(tmp, sizeof tmp, "observed", index);
    if (out == NULL) return 124;
    fprintf(out, "deltaos-fd-receipt 1\nnonce %s\ncase %llu\nstart %d\n", RUN_NONCE,
            (unsigned long long)c.case_id, index);
    fprintf(out, "pid %ld %ld\nruid %ld\neuid %ld\n", (long)getpid(), (long)getppid(),
            (long)getuid(), (long)geteuid());
    fprintf(out, "listed %d %d %d\n", list_errno, total, listed);
    for (int i = 0; i < listed; i++) {
        fprintf(out, "fd %d %d %d ", table[i].fd, table[i].cloexec, table[i].len < 0 ? -table[i].len : 0);
        if (table[i].len > 0) put_hex(out, (const unsigned char *)table[i].target, (size_t)table[i].len);
        fputc('\n', out);
    }
    fprintf(out, "fd3_stat %d %llu %llu %lo\n", stat_errno,
            stat_errno ? 0ULL : (unsigned long long)info.st_dev,
            stat_errno ? 0ULL : (unsigned long long)info.st_ino,
            stat_errno ? 0UL : (unsigned long)info.st_mode);
    fprintf(out, "fd3_flags %d %o\n", flags_errno, flags < 0 ? 0U : (unsigned)flags);
    fprintf(out, "fd3_offset %d %lld\n", offset_errno, offset < 0 ? 0LL : (long long)offset);
    fprintf(out, "fd3_read %d %zu ", read_state, read_count);
    put_hex(out, data, read_count);
    fprintf(out, "\nend\n");
    if (commit(out, tmp, "observed", index) != 0) return 124;

    /* Stay alive until the grader has looked at the caller. stat(), not
     * access(): access() would ask as the real uid, which may not enter here. */
    clock_gettime(CLOCK_MONOTONIC, &started);
    while (c.hold) {
        if (stat(RECEIPT_DIR "/release", &info) == 0) {
            released = 1;
            break;
        }
        if (elapsed_ms(&started) >= (long)c.hold_cap_ms) break;
        nap_ms(1);
    }
    if (c.sleep_ms) nap_ms(c.sleep_ms > 5000 ? 5000 : c.sleep_ms);

    out = begin(tmp, sizeof tmp, "finished", index);
    if (out == NULL) return 124;
    fprintf(out, "finished %llu %s %d\n", (unsigned long long)c.case_id, RUN_NONCE, released);
    if (commit(out, tmp, "finished", index) != 0) return 124;

    if (c.kill_signal) {
        int sig = (int)c.kill_signal;
        sigset_t one;
        prctl(PR_SET_DUMPABLE, 0);      /* never a core file, whatever the signal */
        signal(sig, SIG_DFL);
        sigemptyset(&one);
        sigaddset(&one, sig);
        sigprocmask(SIG_UNBLOCK, &one, NULL);
        kill(getpid(), sig);
        nap_ms(200);
        kill(getpid(), SIGKILL);        /* the signal asked for was not fatal */
    }
    _exit((int)(c.exit_code & 0xff));
}
