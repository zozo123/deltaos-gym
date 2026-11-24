#include "vfs_api.h"
/* BUGS: assumes full writes; renames dirty bytes; no directory sync. */
int publish(struct vfs_api *os, const unsigned char *payload, size_t length) {
    if (os->create_temp(os->ctx) < 0) return -1;
    if (os->write_temp(os->ctx, payload, length) < 0) return -1;
    if (os->rename_temp(os->ctx) < 0) return -1;
    return 0;
}
