# Active observability: choose the smallest diagnostic probe set

A Linux production service intermittently fails. Competing diagnoses span
Python asyncio, a C extension, VFS latency, scheduler delay, and device I/O.
An eBPF tracepoint, user-space probe, ETW-style event, or /proc observation has
a cost and may return more than one value for a given root cause.

Implement `select_probes(case)` in `/workspace/solver.py`. The grading harness
calls your function with a Python dictionary and expects one of:

* `{"selected": ["probe_name", ...], "cost": integer}` for a feasible set;
* `{"selected": null}` when no set satisfies the constraints.

Case schema:

```
{
  "hypotheses": ["python_deadlock", "vfs_stall", "driver_error"],
  "probes": [
    {"name": "sched_switch", "cost": 3,
     "readings": {"python_deadlock": [0], "vfs_stall": [1], "driver_error": [1]}},
    ...
  ],
  "budget": 10,
  "max_probes": 3
}
```

The readings are possible discrete outcomes for each hypothesis. Because
outcomes are nondeterministic, a probe distinguishes a pair only if their
possible outcome sets are **disjoint**. Multiple probe readings are modeled
as independent possibilities conditioned on the hypothesis. A chosen set
must distinguish every pair of hypotheses. Use the minimum total cost;
break ties by number of selected probes, then lexicographic ordered names.
Do not select probes exceeding `budget` or `max_probes`. If no solution
exists, return `{"selected": null}`.

This is a bounded, static **experiment-design** task. It does not prove that
real production eBPF/ETW instrumentation captures every event. The goal is to
design a causally informative measurement plan under a stated observation
model. Only edit `solver.py`.
