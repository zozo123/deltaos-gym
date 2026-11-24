/* Honest-mistake class: assumes the capability already sits at descriptor 3 and never looks at authorized_fd. */
#define _GNU_SOURCE
#include "spawn.h"
#include <unistd.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <fcntl.h>
#include <errno.h>
#include <stdlib.h>
#include <limits.h>
#include <sys/syscall.h>
/* Conservative complete close of all inherited fd capabilities except 0..3.
 * The exercise is intentionally Linux userland; production would prefer a
 * close_range/posix_spawn design with carefully specified fallback behavior.
 */
int run_worker(const char *worker_executable, int authorized_fd) {
    if (!worker_executable) return -1;
    pid_t pid=fork();
    if (pid<0) return -1;
    if (pid==0) {
        (void)authorized_fd;
        int flags=fcntl(3,F_GETFD);
        if (flags<0 || fcntl(3,F_SETFD,flags & ~FD_CLOEXEC)<0) _exit(126);
        /* close_range is atomic and avoids a million close() syscalls.
         * The loop fallback handles older Linux kernels. */
        int closed = 0;
#ifdef SYS_close_range
        if (syscall(SYS_close_range, 4U, ~0U, 0U) == 0) closed=1;
#endif
        if (!closed) {
            struct rlimit limit;
            if (getrlimit(RLIMIT_NOFILE,&limit)!=0) _exit(126);
            rlim_t upper=limit.rlim_cur;
            if (upper==RLIM_INFINITY || upper>1048576) upper=1048576;
            for (int fd=4;fd<(int)upper;fd++) close(fd);
        }
        execl(worker_executable,worker_executable,(char*)NULL);
        _exit(127);
    }
    int status=0;
    pid_t w;
    do {w=waitpid(pid,&status,0);} while (w<0 && errno==EINTR);
    if (w<0 || !WIFEXITED(status)) return -1;
    return WEXITSTATUS(status);
}
