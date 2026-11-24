/* Correct alternative: marks every descriptor from 3 up close-on-exec in one call; dup2 then gives descriptor 3 a fresh, inheritable copy. */
#define _GNU_SOURCE
#include "spawn.h"
#include <errno.h>
#include <fcntl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef CLOSE_RANGE_CLOEXEC
#define CLOSE_RANGE_CLOEXEC (1U << 2)
#endif

int run_worker(const char *worker_executable, int authorized_fd) {
    if (!worker_executable || authorized_fd < 0) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        int source = authorized_fd;
        if (authorized_fd == 3) {
            source = fcntl(3, F_DUPFD_CLOEXEC, 10);
            if (source < 0) _exit(126);
        }
        if (syscall(SYS_close_range, 3U, ~0U, CLOSE_RANGE_CLOEXEC) != 0) _exit(126);
        if (dup2(source, 3) < 0) _exit(126);
        execl(worker_executable, worker_executable, (char *)0);
        _exit(127);
    }
    int status = 0;
    pid_t w;
    do { w = waitpid(pid, &status, 0); } while (w < 0 && errno == EINTR);
    if (w < 0 || !WIFEXITED(status)) return -1;
    return WEXITSTATUS(status);
}
