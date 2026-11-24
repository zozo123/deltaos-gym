#define _GNU_SOURCE
#include "spawn.h"
#include <unistd.h>
#include <sys/wait.h>
/* Broken: extra capabilities are inherited by the worker; FD_CLOEXEC can
 * invalidate the authorized channel when it is already descriptor 3. */
int run_worker(const char *worker_executable, int authorized_fd) {
    pid_t pid=fork();
    if (pid<0) return -1;
    if (pid==0) {
        if (dup2(authorized_fd,3)<0) _exit(126);
        execl(worker_executable,worker_executable,(char*)0);
        _exit(127);
    }
    int status;
    if (waitpid(pid,&status,0)<0) return -1;
    return WIFEXITED(status)?WEXITSTATUS(status):-1;
}
