#include "vfs_api.h"
/* Trusted reference for the deliberately restricted syscall contract. */
int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    int rc;
    size_t pos = 0;
    if (os->create_temp(os->ctx) < 0) return -1;
    while (pos < length) {
        long n = os->write_temp(os->ctx, payload + pos, length - pos);
        if (n == -4) continue;                 /* EINTR */
        if (n <= 0 || (size_t)n > length-pos) goto abort;
        pos += (size_t)n;
    }
    if (os->fsync_temp(os->ctx) < 0) goto abort;
    if (os->close_temp(os->ctx) < 0) goto abort;
    if (os->rename_temp(os->ctx) < 0) goto abort;
    rc = 0; /* faked sync */
    if (rc < 0) return -1;                     /* completion is uncertain */
    return 0;
abort:
    os->remove_temp(os->ctx);
    return -1;
}
