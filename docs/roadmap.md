# Not built yet

Six tasks is a seed, not a benchmark. This is what is missing, most useful first.

- **Tasks from the kernel's fix stream.** Turn bound-fix commits into predicate tasks
  automatically (see [shirudo](shirudo.md)). One exists, written by hand.
- **Mitigations that refuse, not only record.** An `fmod_ret`, LSM or netfilter program
  that blocks the dangerous input, graded against a reproducer in a disposable VM.
- **Concurrency.** The quota task is single-threaded. Map updates from several CPUs
  need a linearizability check.
- **A real filesystem behind the VFS task.** The persistence model is stated and small.
  Agreement with ext4 or XFS under injected faults (dm-flakey, dm-log-writes) is not shown.
- **`io_uring` cancellation, `sched_ext` fairness, ring-buffer loss accounting.** Named
  in the original plan, not started.
- **A measured difficulty curve.** Model results on the current tasks are in the README.
  Tasks that current models fail for the right reasons are the next thing to write.
- **Signed receipts.** Receipts are plain JSON today.
- **The flagship episode.** One request that crosses a Python service, a C worker, the
  filesystem and a BPF policy, with fault injection at every boundary.
