# How the graders are tested

A grader is code that decides who gets paid, so it gets its own tests.

`qa/controls/<task>/` holds candidates with a known right verdict:

- `m*` honest mistakes: plausible wrong solutions. Must get reward 0.
- `x*` exploits: candidates that try to obtain the reward without solving the task. Must get reward 0.
- `p*` correct alternatives: right solutions written differently from the reference. Must get reward 1.

The first line of each file says what it is.

```sh
# as root in a Linux container (uid separation is what the exploit controls test)
python3 scripts/release_qa.py --seeds 5
python3 scripts/release_qa.py --seeds 5 --kernel      # privileged container, disposable VM
python3 scripts/run_controls.py vfs-crash-atomicity --seeds 20
```

`release_qa.py` runs the static checks, the unit tests, then every reference, starter
and control on fresh seeds, validates every receipt, and writes
`qa/reports/release-report.json`. It exits non-zero if a single expectation breaks.

`qa/reports/v05-escape-matrix.json` is the control set as it stood before the rewrite
(the 20 shipped mutants and 27 new candidates) graded by the original v0.5 graders
(`scripts/legacy_escape_matrix.sh`, which needs a copy of the v0.5 release). That run is
the reason this version exists. `qa/reports/kernel-demo-egress.json` is every egress
candidate of that time loaded into a real kernel (`qa/kernel_demo.py`).

Do not run candidates you did not write on a machine you care about. The graders
compile and execute them.
