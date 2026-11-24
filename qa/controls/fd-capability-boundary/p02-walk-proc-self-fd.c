/* Correct alternative: in the child, lists /proc/self/fd and closes every descriptor above 3. */
#define _GNU_SOURCE
#include "spawn.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

int run_worker(const char *worker_executable, int authorized_fd) {
    if (!worker_executable || authorized_fd < 0) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        if (authorized_fd != 3) {
            if (dup2(authorized_fd, 3) < 0) _exit(126);
        } else {
            int flags = fcntl(3, F_GETFD);
            if (flags < 0 || fcntl(3, F_SETFD, flags & ~FD_CLOEXEC) < 0) _exit(126);
        }
        DIR *dir = opendir("/proc/self/fd");
        if (!dir) _exit(126);
        int listing = dirfd(dir), found[2048], count = 0;
        struct dirent *entry;
        while ((entry = readdir(dir)) != NULL && count < 2048) {
            if (entry->d_name[0] < '0' || entry->d_name[0] > '9') continue;
            int fd = atoi(entry->d_name);
            if (fd > 3 && fd != listing) found[count++] = fd;
        }
        closedir(dir);
        for (int i = 0; i < count; i++) close(found[i]);
        execl(worker_executable, worker_executable, (char *)0);
        _exit(127);
    }
    int status = 0;
    pid_t w;
    while ((w = waitpid(pid, &status, 0)) < 0 && errno == EINTR) {}
    if (w < 0) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}
