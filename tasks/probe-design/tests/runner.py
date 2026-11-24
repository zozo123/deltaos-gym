"""Runs in the sandbox next to the candidate: loads solver.py and answers every case.

Only protocol glue. The answers go to the descriptor that was stdout at start; anything
the candidate prints lands on stderr. Nothing here is trusted: the grader validates the
answers and compares them with its own oracle.
"""
import importlib.util
import json
import os
import sys

answers_out = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
cases = json.load(sys.stdin)
spec = importlib.util.spec_from_file_location("candidate_solver", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
answers = [module.select_probes(json.loads(json.dumps(case))) for case in cases]
answers_out.write(json.dumps(answers))
answers_out.flush()
