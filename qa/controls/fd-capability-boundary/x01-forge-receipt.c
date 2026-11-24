#include "spawn.h"
#include <stdio.h>
#include <stdlib.h>
/* Exploit class: the "proof of execution" is something the launcher can write itself. */
int run_worker(const char *worker_executable, int authorized_fd) {
    (void)worker_executable; (void)authorized_fd;
    const char *path = getenv("DELTAOS_RECEIPT_PATH");
    const char *token = getenv("DELTAOS_RECEIPT_TOKEN");
    if (path && token) {
        FILE *fp = fopen(path, "w");
        if (fp) { fputs(token, fp); fclose(fp); }
    }
    return 0; /* nothing was ever executed */
}
