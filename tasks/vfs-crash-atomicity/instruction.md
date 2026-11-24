# Atomic publish under crashes, short writes and I/O errors

A "Run" action publishes a generated artifact through a short sequence of file-system
calls. A crash can happen between any two of them, and any call can fail. The current
`/workspace/publisher.c` returns success even though a crash can lose or tear the file.

Fix `publish()`. Keep the ABI in `vfs_api.h` unchanged, and read its comment: it states
exactly how the calls behave.

## Requirements

1. Return `0` only when the complete new content is durably published.
2. After a crash at any point, the published file holds either the old content or the
   complete new content. Never a torn or partial file.
3. Handle short writes, interrupted writes (`-EINTR`, call again) and I/O errors.
4. If no I/O error happened, publishing must succeed. Short writes and `-EINTR` are
   not errors.
5. Work for empty, small and multi-block payloads, and finish in a bounded number of
   calls.
6. Act only through the `vfs_api` calls: no other library or system calls, no inline
   assembly. `memcpy`, `memmove`, `memset` and `memcmp` are fine.

The important Linux behaviours are in the header: a failed `fsync` is reported once and
a later successful `fsync` of the same inode does not bring the lost writes back; an
error from `close()` does not undo data that `fsync` already made durable; a failed
directory `fsync` cannot be repaired by calling it again.

## What the judge does

It links your `publish()` against its own implementation of `vfs_api` and keeps a model
of what is on disk. For payloads of 0 to 3 bytes it explores every schedule: every
possible short write, up to two interrupted writes and up to two I/O errors at any call.
For each schedule it checks what a crash would leave at every point, and what your
return value claims. It then samples schedules for 39, 1001 and 4096-byte payloads, and
checks that the same schedule always produces the same calls.

This is a model of Linux semantics, stated in the header. It is not a test of ext4, XFS
or real disks.
