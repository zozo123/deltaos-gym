/* Correct alternative: after a write, fsync or close error, removes the temporary file and tries once more with a new inode from byte 0. */
#include "vfs_api.h"

static int prepare(struct vfs_api *os, const unsigned char *payload, size_t length) {
    size_t pos = 0;
    if (os->create_temp(os->ctx) < 0) return -1;
    while (pos < length) {
        long n = os->write_temp(os->ctx, payload + pos, length - pos);
        if (n == -4) continue;
        if (n <= 0 || (size_t)n > length - pos) goto undo;
        pos += (size_t)n;
    }
    if (os->fsync_temp(os->ctx) < 0) goto undo;
    if (os->close_temp(os->ctx) < 0) goto undo;
    return 0;
undo:
    os->close_temp(os->ctx);
    os->remove_temp(os->ctx);
    return -1;
}

int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    if (prepare(os, payload, length) < 0 && prepare(os, payload, length) < 0) return -1;
    if (os->rename_temp(os->ctx) < 0) {
        os->remove_temp(os->ctx);
        return -1;
    }
    return os->fsync_directory(os->ctx) < 0 ? -1 : 0;
}
