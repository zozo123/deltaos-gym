/* Correct alternative: once fsync has succeeded the data is durable, so an error from close() is ignored. */
#include "vfs_api.h"

int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    size_t pos = 0;
    if (os->create_temp(os->ctx) < 0) return -1;
    while (pos < length) {
        long n = os->write_temp(os->ctx, payload + pos, length - pos);
        if (n == -4) continue;
        if (n <= 0 || (size_t)n > length - pos) goto abort;
        pos += (size_t)n;
    }
    if (os->fsync_temp(os->ctx) < 0) goto abort;
    (void)os->close_temp(os->ctx);
    if (os->rename_temp(os->ctx) < 0) goto abort;
    return os->fsync_directory(os->ctx) < 0 ? -1 : 0;
abort:
    os->remove_temp(os->ctx);
    return -1;
}
