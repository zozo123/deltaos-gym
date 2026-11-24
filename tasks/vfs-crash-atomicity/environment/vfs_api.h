#ifndef DELTAOS_VFS_API_H
#define DELTAOS_VFS_API_H
#include <stddef.h>
#include <stdint.h>
/* A syscall-level interface for publishing one file atomically in one directory:
 * an O_TMPFILE-style temporary inode, write, fsync, renameat, directory fsync.
 * Every call returns a nonnegative value on success or a negative errno.
 *
 * The judge answers these calls from a persistence model with Linux semantics
 * ("restricted-vfs-crash-v2"). It is a model, not ext4 or XFS:
 *
 *  create_temp      a new empty inode under the temporary name, with an open descriptor.
 *                   -EEXIST while the temporary name exists. May fail with -EIO.
 *  write_temp       appends to the inode behind the descriptor and returns how many
 *                   bytes it took, which can be fewer than offered (a short write).
 *                   -EINTR means nothing was written: call again. -EBADF when the
 *                   descriptor is closed. May fail with -EIO. Any write makes the
 *                   inode's data unsynced, also after the rename.
 *  fsync_temp       makes the inode's data durable. -EBADF on a closed descriptor.
 *                   A failed fsync (-EIO) is reported once: the kernel may already
 *                   have dropped the dirty pages, so a later successful fsync of the
 *                   same inode does not make the earlier writes durable. Only a new
 *                   inode (remove_temp, then create_temp) starts clean again.
 *  close_temp       closes the descriptor, even when it reports -EIO. An error from
 *                   close does not undo data that fsync already made durable.
 *                   A second close is -EBADF.
 *  rename_temp      atomically replaces the published file with the temporary inode;
 *                   the temporary name is gone afterwards. -ENOENT without one.
 *  fsync_directory  makes the rename durable. A failed directory fsync is reported
 *                   once and cannot be repaired by calling it again.
 *  remove_temp      unlinks the temporary name. -ENOENT when there is none.
 *
 * A crash can happen between any two calls. After a crash the published file is
 * the old content until the rename is durable, and after that the new inode's
 * content. An inode survives a crash intact only if a successful fsync came after
 * its creation and after its last write, and no fsync of it ever failed; otherwise
 * it survives torn.
 */
struct vfs_api {
    void *ctx;
    int (*create_temp)(void *ctx);
    long (*write_temp)(void *ctx, const unsigned char *data, size_t n);
    int (*fsync_temp)(void *ctx);
    int (*rename_temp)(void *ctx);
    int (*fsync_directory)(void *ctx);
    int (*close_temp)(void *ctx);
    int (*remove_temp)(void *ctx);
};

/* Return 0 only when the complete new content has been durably published.
 * Otherwise return a nonzero value. */
int publish(struct vfs_api *os, const unsigned char *payload, size_t length);
#endif
