# Capability confinement across fork and exec

A Python control plane calls a C launcher to start an untrusted tool: a code runner,
a compiler worker, an AI agent's subprocess. The tool must receive exactly one data
capability, at file descriptor 3, and nothing else the control plane holds.

Fix `/workspace/spawn.c`. Keep the ABI in `spawn.h`:

```c
int run_worker(const char *worker_executable, int authorized_fd);
```

## Requirements

1. The worker starts with descriptor 3 referring to the **same open file description**
   as `authorized_fd` (same file, same offset; not a reopened copy).
2. No descriptor above 2 other than 3 survives `exec`: not inherited secrets, decoys,
   directories, pipes, sockets or duplicates, whatever their numbers (some are above 255).
3. If `authorized_fd` is already 3, clear its close-on-exec flag so it survives.
4. The caller's own descriptor table is unchanged afterwards: the same descriptors,
   pointing at the same things, with the same flags. Do the plumbing in the child.
5. Return `0` only if the worker ran and exited with status 0. Return non-zero if it
   exited non-zero, died from a signal, could not be started, or if `authorized_fd` is
   not an open descriptor.
6. Wait for the worker before returning, and keep waiting when `waitpid` is interrupted
   by a signal (`EINTR`): the caller receives `SIGALRM` every few milliseconds in some
   cases. Leave no zombie.
7. Start the worker exactly once. Do not hardcode paths, descriptor numbers other than
   3, or file contents.

## What the judge does

It runs real launches on Linux, as root with the caller under one uid and the worker
installed setuid to another, so only an exec'ed worker can leave a receipt. The worker
records the descriptor table it received and reads from descriptor 3. The judge reads
the caller's table from `/proc` before and after the call, and checks for leftover
children. Layouts are drawn fresh for each episode: the authorized descriptor at 3, 5,
8, 11, 57 or a random number, with and without close-on-exec, a decoy at 3, other
capabilities up to descriptor 900; workers that succeed, fail, die from a signal or run
slowly while the caller is interrupted; a closed `authorized_fd`; a missing worker.

These are real kernel semantics, tested, not a proof.
