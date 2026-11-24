#ifndef DELTAOS_VFS_API_H
#define DELTAOS_VFS_API_H
#include <stddef.h>
#include <stdint.h>
/* Restricted syscall-level interface modeling one-directory atomic publish.
 * This is NOT a replacement for testing Linux on a real filesystem.
 * All return values are nonnegative success or negative errno.
 */
struct vfs_api {
    void *ctx;
    int (*create_temp)(void *ctx);                  /* exclusive temporary inode */
    long (*write_temp)(void *ctx, const unsigned char *data, size_t n);
    int (*fsync_temp)(void *ctx);
    int (*rename_temp)(void *ctx);                 /* atomically replace current */
    int (*fsync_directory)(void *ctx);
    int (*close_temp)(void *ctx);
    int (*remove_temp)(void *ctx);
};
/* Return 0 only when new content has been durably published. */
int publish(struct vfs_api *os, const unsigned char *payload, size_t length);
#endif
