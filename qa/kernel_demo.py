#!/usr/bin/env python3
"""What the egress candidates do when they are really loaded into the kernel.

For the reference and every egress control: build the cgroup/connect4 object exactly
as the grader does, load it, attach it to a fresh cgroup and make the grader's 192
connect() calls. Reports how many decisions differ from the contract. Root, privileged
container, disposable VM only. Output: JSON on stdout.
"""
import importlib.util, json, pathlib, platform, subprocess, sys, tempfile
ROOT = pathlib.Path(sys.argv[1])
TESTS = ROOT / "tasks/egress-policy-delta/tests"
sys.path.insert(0, str(TESTS))
spec = importlib.util.spec_from_file_location("egress_grade", TESTS / "grade.py")
grade = importlib.util.module_from_spec(spec); spec.loader.exec_module(grade)
H = grade.H
flows = grade.kernel_flows()
rows = []
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    subprocess.run(["gcc", "-O2", str(TESTS / "kernel_check.c"), "-o", str(tmp / "kc"), "-lbpf", "-lelf", "-lz"], check=True)
    cands = [("reference", ROOT / "tasks/egress-policy-delta/solution/policy.c"),
             ("starter", ROOT / "tasks/egress-policy-delta/environment/policy.c")]
    cands += [(p.name, p) for p in sorted((ROOT / "qa/controls/egress-policy-delta").iterdir()) if p.suffix == ".c"]
    for name, path in cands:
        work = tmp / name; work.mkdir()
        (work / "policy.c").write_bytes(path.read_bytes())
        (work / "bpf_adapter.c").write_bytes((TESTS / "bpf_adapter.c").read_bytes())
        pre = subprocess.run(["clang", "-target", "bpf", "-ffreestanding", "-E", "-P", "policy.c", "-o", "candidate.i"], cwd=work, capture_output=True)
        obj = subprocess.run(["clang", *H.bpf_cflags(), "-c", "bpf_adapter.c", "-o", "prog.bpf.o"], cwd=work, capture_output=True)
        if pre.returncode or obj.returncode:
            rows.append({"candidate": name, "loaded": False, "stage": "compile"}); continue
        out = subprocess.run([str(tmp / "kc"), str(work / "prog.bpf.o")], input="".join("%d %d %d %d\n" % f for f in flows), capture_output=True, text=True, timeout=120)
        seen = json.loads(out.stdout)
        if not seen.get("loaded") or "decisions" not in seen:
            rows.append({"candidate": name, "loaded": bool(seen.get("loaded")), "stage": seen.get("stage")}); continue
        want = [grade.contract(*f, int(f == grade.BASELINE)) for f in flows]
        got = seen["decisions"]
        wrong = [(f, w, g) for f, w, g in zip(flows, want, got) if w != g]
        rows.append({"candidate": name, "loaded": True, "connects": len(flows),
                     "allowed": sum(got), "should_allow": sum(want),
                     "wrongly_allowed": sum(1 for _, w, g in wrong if g == 1),
                     "wrongly_denied": sum(1 for _, w, g in wrong if g == 0),
                     "example": ({"uid": wrong[0][0][0], "ip": ".".join(str((wrong[0][0][1] >> s) & 255) for s in (24, 16, 8, 0)),
                                  "port": wrong[0][0][2], "proto": wrong[0][0][3], "contract": wrong[0][1], "kernel": wrong[0][2]} if wrong else None)})
print(json.dumps({"kernel_release": platform.release(), "machine": platform.machine(), "rows": rows}, indent=1))
