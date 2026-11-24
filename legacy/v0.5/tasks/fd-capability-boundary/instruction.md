# Capability confinement across fork/exec: C, Python, and Linux file descriptors

A Python control plane delegates work to a C launcher. The launcher executes an
untrusted tool process that should inherit **exactly one** authorized data
capability: file descriptor 3. In production this could be a code runner,
compiler worker, or AI agent subprocess.

Fix `/workspace/spawn.c`, keeping `spawn.h` ABI unchanged:

    int run_worker(const char *worker_executable, int authorized_fd);

Required properties:

1. Child executable receives a readable authorized descriptor at fd 3.
2. No other fd >= 4 survives `exec`, including inherited secret handles,
   directories, sockets, duplicate capabilities, or unexpected parent fds.
3. When `authorized_fd` is already fd 3, still clear `FD_CLOEXEC` so it survives.
4. The Python parent retains all original fd capabilities after the call.
5. Return 0 only if the trusted worker exits successfully, and propagate failure
   status as a nonzero result. Handle interrupted `waitpid` correctly.
   The judge independently requires an execution receipt produced by the child.
6. Do not hardcode grader-specific paths, fd numbers other than the ABI slot 3,
   or expected data contents.

The independent judge launches actual Linux processes. It verifies descriptor
state in the child process *after exec*, checks the data channel, and checks
that the caller's fds remain open. Different randomized descriptor layouts,
CLOEXEC flags and private extra handles are tested. These are real kernel
fd-table and exec semantics, not a synthetic eBPF model. The test is not a
formal proof against malicious kernel behavior.
