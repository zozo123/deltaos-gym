#!/usr/bin/env python3
"""Agent-owned Python only runs in the isolated verifier environment."""
import importlib.util, json, pathlib, sys
p=pathlib.Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('candidate_solver',p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cases=json.load(sys.stdin)
answers=[]
for c in cases:
    answers.append(mod.select_probes(c))
json.dump(answers,sys.stdout)
