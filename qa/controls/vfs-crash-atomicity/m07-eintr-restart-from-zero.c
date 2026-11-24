#include "vfs_api.h"
/* Honest-mistake class: on EINTR starts the payload again from byte 0 without truncating. */
int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    int rc;
    size_t pos = 0;
    if (os->create_temp(os->ctx) < 0) return -1;
    while (pos < length) {
        long n = os->write_temp(os->ctx, payload + pos, length - pos);
        if (n == -4) { pos = 0; continue; }    /* EINTR */
        if (n <= 0 || (size_t)n > length-pos) goto abort;
        pos += (size_t)n;
    }
    if (os->fsync_temp(os->ctx) < 0) goto abort;
    if (os->close_temp(os->ctx) < 0) goto abort;
    if (os->rename_temp(os->ctx) < 0) goto abort;
    rc = os->fsync_directory(os->ctx);
    if (rc < 0) return -1;                     /* completion is uncertain */
    return 0;
abort:
    os->remove_temp(os->ctx);
    return -1;
}
