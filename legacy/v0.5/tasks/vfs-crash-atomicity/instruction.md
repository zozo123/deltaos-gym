# Atomic publish after failures and crashes

A desktop "Run" action publishes a generated workspace artifact through a
Linux-style VFS operation sequence. A process crash or I/O error can occur
at any step. The current implementation in `/workspace/publisher.c` returns
success even though a system crash could lose or corrupt the new artifact.

Fix `publish()` while keeping the ABI in `vfs_api.h` unchanged.

Requirements:

1. A successful return means the complete new byte sequence has been
   durably published. Never return success early.
2. A crash after any syscall-like step may leave the old complete bytes or
   the new complete bytes, never a torn/truncated result.
3. Handle short positive writes, EINTR on writes, and I/O failures.
4. Do not destroy the old complete value before the new value is ready.
5. Work for empty, small, and multi-block payloads.
6. Make the minimal correct change to `publisher.c`; the verifier compiles
   the candidate independently with its own copy of the public ABI.

You may inspect `vfs_api.h` and use compiler/debugger tools. The API models
an `openat` temporary inode, `write`, file `fsync`, atomic `renameat`, and
parent directory `fsync`. The verifier explores crash cuts and error paths
in a *restricted, documented persistence model*. It does not establish
ext4, XFS, overlayfs, or power-loss correctness on real hardware.
