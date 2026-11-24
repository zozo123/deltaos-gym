#!/usr/bin/env python3
"""Grader for probe-design: an exact oracle on fixed, directed and fresh random instances.

The candidate's solver runs only in the sandbox (python3 -I, scrubbed environment, as
another user when the grader is root). Answers are validated field by field and type by
type, then compared with an oracle that enumerates every feasible probe set.
"""
import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deltaos_harness as H  # noqa: E402

TASK = "deltaos/probe-design"
MODEL = "finite-experiment-design/2"


def oracle(case):
    """Cheapest set of probes that separates every pair; ties: fewer probes, then names."""
    hyps = case["hypotheses"]
    probes = case["probes"]
    pairs = list(itertools.combinations(range(len(hyps)), 2))
    separates = []
    for probe in probes:
        mask = 0
        for bit, (a, b) in enumerate(pairs):
            if not set(probe["readings"][hyps[a]]) & set(probe["readings"][hyps[b]]):
                mask |= 1 << bit
        separates.append(mask)
    everything = (1 << len(pairs)) - 1
    best = None
    for size in range(0, min(case["max_probes"], len(probes)) + 1):
        for chosen in itertools.combinations(range(len(probes)), size):
            cost = sum(probes[i]["cost"] for i in chosen)
            if cost > case["budget"]:
                continue
            covered = 0
            for i in chosen:
                covered |= separates[i]
            if covered != everything:
                continue
            key = (cost, size, sorted(probes[i]["name"] for i in chosen))
            if best is None or key < best:
                best = key
    return {"selected": None} if best is None else {"selected": best[2], "cost": best[0]}


def probe(name, cost, readings):
    return {"name": name, "cost": cost, "readings": readings}


def directed_cases():
    two = ["a", "b"]
    return [
        # the three v0.5 cases
        {"hypotheses": two, "budget": 5, "max_probes": 2,
         "probes": [probe("eBPF", 3, {"a": [0, 1], "b": [1, 2]}), probe("ptrace", 4, {"a": [0], "b": [1]})]},
        {"hypotheses": two, "budget": 2, "max_probes": 1,
         "probes": [probe("only", 2, {"a": [1, 2], "b": [2, 3]})]},
        {"hypotheses": ["a", "b", "c"], "budget": 7, "max_probes": 1,
         "probes": [probe("all_one", 1, {"a": [0], "b": [0], "c": [0]}),
                    probe("pair_a", 2, {"a": [0], "b": [1], "c": [1]}),
                    probe("pair_b", 2, {"a": [1], "b": [0], "c": [1]})]},
        # one hypothesis: nothing to separate, the empty set at cost 0
        {"hypotheses": ["only"], "budget": 5, "max_probes": 2, "probes": [probe("p", 1, {"only": [0]})]},
        # no probes at all
        {"hypotheses": two, "budget": 5, "max_probes": 3, "probes": []},
        # max_probes 0
        {"hypotheses": two, "budget": 5, "max_probes": 0, "probes": [probe("p", 1, {"a": [0], "b": [1]})]},
        # readings always overlap: no solution
        {"hypotheses": two, "budget": 50, "max_probes": 3,
         "probes": [probe("x", 1, {"a": [0, 1], "b": [1]}), probe("y", 1, {"a": [2], "b": [2, 3]})]},
        # equal cost: one probe beats two
        {"hypotheses": ["a", "b", "c"], "budget": 9, "max_probes": 3,
         "probes": [probe("solo", 4, {"a": [0], "b": [1], "c": [2]}),
                    probe("half1", 2, {"a": [0], "b": [1], "c": [1]}),
                    probe("half2", 2, {"a": [0], "b": [0], "c": [1]})]},
        # equal cost and size: names decide
        {"hypotheses": two, "budget": 9, "max_probes": 2,
         "probes": [probe("zeta", 3, {"a": [0], "b": [1]}), probe("alpha", 3, {"a": [5], "b": [6]})]},
        # zero-cost probes: a free separating probe, and a free useless one that must not be added
        {"hypotheses": two, "budget": 0, "max_probes": 3,
         "probes": [probe("free", 0, {"a": [0], "b": [1]}), probe("noise", 0, {"a": [0], "b": [0]})]},
        # budget exactly the optimum, then one less
        {"hypotheses": ["a", "b", "c"], "budget": 5, "max_probes": 2,
         "probes": [probe("p1", 2, {"a": [0], "b": [1], "c": [1]}), probe("p2", 3, {"a": [0], "b": [0], "c": [1]})]},
        {"hypotheses": ["a", "b", "c"], "budget": 4, "max_probes": 2,
         "probes": [probe("p1", 2, {"a": [0], "b": [1], "c": [1]}), probe("p2", 3, {"a": [0], "b": [0], "c": [1]})]},
    ]


def random_case(rng, hypotheses, probes, max_probes):
    hyps = ["h" + str(j) for j in range(hypotheses)]
    items = []
    for j in range(probes):
        readings = {}
        for h in hyps:
            v = rng.randrange(5)
            readings[h] = [v] if rng.random() < 0.56 else sorted({v, (v + rng.choice([1, 2, 3])) % 5})
        items.append(probe("probe_" + str(j).zfill(2), rng.randrange(1, 12), readings))
    rng.shuffle(items)
    return {"hypotheses": hyps, "budget": rng.randint(2, 40), "max_probes": max_probes, "probes": items}


def build_cases(rng):
    cases = directed_cases()
    for _ in range(300):
        n = rng.randint(3, 11)
        cases.append(random_case(rng, rng.randint(2, 7), n, rng.randint(1, min(7, n))))
    for _ in range(6):
        cases.append(random_case(rng, rng.randint(4, 7), rng.randint(12, 14), rng.randint(4, 7)))
    return cases


def well_formed(answer, case):
    if not isinstance(answer, dict) or "selected" not in answer:
        return "each answer must be a dict with a 'selected' key"
    selected = answer["selected"]
    if selected is None:
        return None if set(answer) == {"selected"} else "an answer with selected null has no other keys"
    if set(answer) != {"selected", "cost"}:
        return "an answer with a probe list has exactly the keys 'selected' and 'cost'"
    if not isinstance(selected, list) or not all(isinstance(n, str) for n in selected):
        return "'selected' must be a list of probe names"
    if selected != sorted(set(selected)):
        return "'selected' must be sorted and without duplicates"
    if not set(selected) <= {p["name"] for p in case["probes"]}:
        return "'selected' names a probe that does not exist"
    cost = answer["cost"]
    if type(cost) is not int:
        return "'cost' must be an int"
    return None


def body(ctx):
    receipt, sbx = ctx.receipt, ctx.sandbox
    source = H.read_artifact("solver.py")
    receipt.artifact("solver.py", source)
    cases = build_cases(ctx.rng("cases"))
    expected = [oracle(case) for case in cases]
    sbx.put("solver.py", source)
    sbx.put("runner.py", (H.TESTS / "runner.py").read_bytes())
    run = sbx.run(["python3", "-I", str(sbx.path("runner.py")), str(sbx.path("solver.py"))],
                  input=json.dumps(cases).encode(), timeout=90,
                  limits={"cpu": 90, "as": 4096 * H.MiB, "fsize": 64 * H.MiB, "nofile": 256})
    if not run.ok:
        receipt.check("solver_runs", False)
        raise H.Reject("solver_crashed_or_timed_out", exit=run.returncode, timed_out=run.timed_out,
                       log=run.stderr.decode("utf-8", "replace")[-800:])
    try:
        answers = json.loads(run.stdout)
    except ValueError:
        receipt.check("solver_runs", False)
        raise H.Reject("solver_output_is_not_json")
    if not isinstance(answers, list) or len(answers) != len(cases):
        receipt.check("solver_runs", False)
        raise H.Reject("wrong_number_of_answers", expected=len(cases),
                       actual=len(answers) if isinstance(answers, list) else None)
    receipt.check("solver_runs", True)
    for index, (case, answer, want) in enumerate(zip(cases, answers, expected)):
        problem = well_formed(answer, case)
        if problem:
            receipt.check("exact_optimum", False)
            raise H.Reject("malformed_answer", index=index, problem=problem, answer=answer, case=case)
        if answer != want:
            receipt.check("exact_optimum", False)
            raise H.Reject("not_the_optimum", index=index, expected=want, actual=answer, case=case)
    receipt.check("exact_optimum", True)
    receipt.extra["cases_executed"] = len(cases)
    receipt.add_evidence("TESTED", "select_probes returns the exact optimum with the stated tie-breaks", "pass",
                         f"{len(cases)} instances: the 3 original cases, 9 directed edge cases, "
                         f"{len(cases) - 12} instances drawn fresh for this episode (up to 14 probes); "
                         "each compared with an oracle that enumerates every feasible set",
                         cases=len(cases))


if __name__ == "__main__":
    sys.exit(H.run_grader(TASK, MODEL, body))
