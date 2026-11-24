# Active observability: choose the cheapest probe set that tells the causes apart

A Linux service fails intermittently. Several root causes are possible: Python asyncio,
a C extension, VFS latency, scheduler delay, device I/O. Each available probe (an eBPF
tracepoint, a user-space probe, a `/proc` reading) has a cost, and for each cause it
can return one of several values.

Implement `select_probes(case)` in `/workspace/solver.py`.

## Input

```python
{
  "hypotheses": ["python_deadlock", "vfs_stall", "driver_error"],
  "probes": [
    {"name": "sched_switch", "cost": 3,
     "readings": {"python_deadlock": [0], "vfs_stall": [1], "driver_error": [1, 2]}},
    ...
  ],
  "budget": 10,
  "max_probes": 3
}
```

`readings[h]` lists the values the probe can show when `h` is the cause. A probe
separates two causes only if their value lists are **disjoint**: otherwise one value
could come from either.

## Output

- `{"selected": [names...], "cost": total}` for the chosen set: every pair of causes is
  separated by at least one selected probe, the total cost is at most `budget`, and at
  most `max_probes` probes are selected.
- Choose the minimum total cost. Break ties by fewer probes, then by the sorted list of
  names compared lexicographically.
- `selected` is sorted, has no duplicates, and names only existing probes; `cost` is a
  Python `int`; the dict has exactly these two keys.
- With a single cause there is nothing to separate: `{"selected": [], "cost": 0}`.
- If no set qualifies: `{"selected": None}` and no other key.

Do not print anything; only the return value counts. Only edit `solver.py`.

## What the judge does

Runs your function in a sandbox on the original three cases, a set of edge cases (one
cause, no probes, `max_probes` 0, unsatisfiable, every tie-break, zero-cost probes,
budget at and just below the optimum) and about 300 instances drawn fresh for each
episode, some with 14 probes. Each answer is compared with an oracle that enumerates
every feasible set.

This is a static experiment-design problem under a stated observation model. It does
not claim that real instrumentation sees every event.
