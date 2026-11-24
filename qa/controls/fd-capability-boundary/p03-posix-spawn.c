/* Correct alternative: posix_spawn with two file actions, dup2 to 3 (which also clears close-on-exec when it is already 3) and close everything from 4 up. */
#define _GNU_SOURCE
#include "spawn.h"
#include <spawn.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

int run_worker(const char *worker_executable, int authorized_fd) {
    if (!worker_executable || authorized_fd < 0 || fcntl(authorized_fd, F_GETFD) < 0) return -1;
    posix_spawn_file_actions_t actions;
    if (posix_spawn_file_actions_init(&actions) != 0) return -1;
    int ready = posix_spawn_file_actions_adddup2(&actions, authorized_fd, 3) == 0 &&
                posix_spawn_file_actions_addclosefrom_np(&actions, 4) == 0;
    pid_t pid;
    char *const argv[] = {(char *)worker_executable, NULL};
    int rc = ready ? posix_spawn(&pid, worker_executable, &actions, NULL, argv, environ) : -1;
    posix_spawn_file_actions_destroy(&actions);
    if (rc != 0) return -1;
    int status = 0;
    pid_t w;
    do { w = waitpid(pid, &status, 0); } while (w < 0 && errno == EINTR);
    if (w < 0 || !WIFEXITED(status)) return -1;
    return WEXITSTATUS(status);
}
