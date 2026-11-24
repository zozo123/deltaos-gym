/* Correct alternative: keeps the descriptor open across the rename and closes it last; a close error after the directory fsync does not matter. */
#include "vfs_api.h"

int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    size_t pos = 0;
    int rc;
    if (os->create_temp(os->ctx) < 0) return -1;
    while (pos < length) {
        long n = os->write_temp(os->ctx, payload + pos, length - pos);
        if (n == -4) continue;
        if (n <= 0 || (size_t)n > length - pos) goto fail;
        pos += (size_t)n;
    }
    if (os->fsync_temp(os->ctx) < 0) goto fail;
    if (os->rename_temp(os->ctx) < 0) goto fail;
    rc = os->fsync_directory(os->ctx);
    os->close_temp(os->ctx);
    return rc < 0 ? -1 : 0;
fail:
    os->close_temp(os->ctx);
    os->remove_temp(os->ctx);
    return -1;
}
