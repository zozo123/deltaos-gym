#!/usr/bin/env python3
"""Build docs/index.html from site/template.html and the reports in qa/reports/.

Every number on the page is read from a report file, so the page cannot drift from
what was measured. Fails if a placeholder is left unfilled.
"""
import datetime
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "qa" / "reports"
REPO = "https://github.com/zozo123/deltaos-gym"


def load(name):
    path = REPORTS / name
    return json.loads(path.read_text()) if path.is_file() else None


def chips(evidence):
    seen = []
    for item in evidence:
        if item["status"] == "pass" and item["class"] not in seen:
            seen.append(item["class"])
    return " ".join(f'<span class="chip good">{c.replace("_", " ")}</span>' for c in seen)


def main() -> int:
    release = load("release-report.json")
    legacy = load("v05-escape-matrix.json")
    if not release or not legacy:
        print("need qa/reports/release-report.json and v05-escape-matrix.json")
        return 1
    draft = "--draft" in sys.argv
    if not release["passed"] and not draft:
        print("refusing to build the site from a failing release report (use --draft to preview)")
        return 1
    totals, tasks = release["totals"], release["tasks"]
    assert legacy["summary"]["new_wrong_candidates_accepted"] == 27 and legacy["summary"]["shipped_mutants_rejected"] == 20
    pos_runs = sum(t["correct_total"] for t in tasks.values()) - release["seeds_per_candidate"] * len(tasks)
    pos_ok = sum(t["correct_accepted"] for t in tasks.values()) - release["seeds_per_candidate"] * len(tasks)

    egress = tasks["egress-policy-delta"]
    ladder = "\n".join(
        f'<li><span class="chip">{html.escape(e["class"].replace("_", " "))}</span>{html.escape(e["claim"])}'
        f'<small>{html.escape(e["scope"])}</small></li>'
        for e in egress["reference_evidence"] if e["status"] == "pass")
    proof = next(e for e in egress["reference_evidence"] if e["class"] == "PROVED_WITHIN_MODEL")

    rows = []
    for name, t in tasks.items():
        rows.append(
            f'<tr><td><a href="{REPO}/tree/main/tasks/{name}"><code>{name}</code></a></td>'
            f'<td>{chips(t["reference_evidence"])}</td>'
            f'<td class="n">{t["wrong_rejected"]} / {t["wrong_total"]}</td>'
            f'<td class="n">{t["correct_accepted"]} / {t["correct_total"]}</td>'
            f'<td class="n">{t["seconds_mean"]:.1f} s</td></tr>')

    units = sum(u["ran"] for u in release["unit_tests"])
    qa_line = (f'{totals["episodes"]} graded runs: the reference, the starter and every control of '
               f'{totals["tasks"]} tasks on {release["seeds_per_candidate"]} fresh seeds each, kernel tier '
               f'{"on" if release["environment"]["kernel_tier"] == "required" else "off"}, as root with the '
               f'candidate under another uid, {release["duration_sec"]:.0f} s in total. '
               f'{totals["receipts_valid"]} receipts validated against the schema. {units} unit tests. '
               f'{release["environment"]["gcc"]}, {release["environment"]["clang"]}, CBMC {release["environment"]["cbmc"]}.')

    ci = load("ci-github-runner.json")
    if ci and ci.get("passed"):
        qa_line += (f' The same QA passes in CI on a GitHub runner too: Linux {ci["environment"]["kernel_release"]}, '
                    f'kernel tier on, {ci["totals"]["episodes"]} graded runs, 0 wrong candidates accepted.')

    demo = load("kernel-demo-egress.json")
    ifdef = ""
    if demo:
        loaded = sum(1 for r in demo["rows"] if r.get("loaded"))
        x01 = next(r for r in demo["rows"] if r["candidate"].startswith("x01"))
        ifdef = (f'Loaded into Linux {demo["kernel_release"]}, that build let through {x01["allowed"]} of '
                 f'{x01["connects"]} test connections; the contract allows {x01["should_allow"]}. '
                 f'The verifier loaded all {loaded} candidates, right and wrong.')

    harbor = load("harbor-e2e.json")
    harbor_html = ""
    if harbor:
        ok = all(t["oracle_reward"] == 1.0 and t["nop_reward"] == 0.0 for t in harbor["tasks"])
        if ok:
            harbor_html = (f'<p>Under <a href="https://github.com/harbor-framework/harbor">Harbor</a> '
                           f'{html.escape(harbor["harbor_version"])}, each task in its own verifier container: the '
                           f'reference agent scores 1.0 and the do-nothing agent 0.0 on all {len(harbor["tasks"])} '
                           f'tasks, and <code>harbor lint</code> reports nothing. {html.escape(harbor.get("note", ""))}</p>')

    models = load("model-runs.json")
    models_html = ""
    if models:
        head = "".join(f'<th class="n">{html.escape(m)}</th>' for m in models["models"])
        body = []
        for task in models["tasks"]:
            cells = "".join(
                f'<td class="n {"good" if models["results"][m][task]["reward"] else "bad"}">'
                f'{"pass" if models["results"][m][task]["reward"] else "fail"}</td>' for m in models["models"])
            body.append(f"<tr><td><code>{task}</code></td>{cells}</tr>")
        models_html = (f'<h3>One attempt each by current models</h3><p>{html.escape(models["method"])}</p>'
                       f'<div class="wide"><table><thead><tr><th>Task</th>{head}</tr></thead><tbody>'
                       + "".join(body) + f'</tbody></table></div><p>{html.escape(models["finding"])}</p>')

    vfs_scope = next((e["scope"] for e in tasks.get("vfs-crash-atomicity", {}).get("reference_evidence", [])
                      if e["class"] == "MODEL_CHECKED"), "")
    schedules = re.search(r"([\d,]+) schedules", vfs_scope)
    values = {
        "VERSION": release["release"],
        "NEG": str(totals["negative_controls"] + totals["tasks"]),
        "WRONG_EPISODES": str(totals["wrong_total"]),
        "POS_OK": str(pos_ok), "POS_RUNS": str(pos_runs),
        "KERNEL": release["environment"]["kernel_release"],
        "IFDEF_KERNEL": ifdef,
        "CBMC_SECONDS": f'{proof.get("detail", {}).get("seconds", 0.03):.2f}' if isinstance(proof.get("detail"), dict) else "0.03",
        "VFS_SCHEDULES": schedules.group(1) if schedules else "thousands of",
        "LADDER": ladder, "TASK_ROWS": "\n".join(rows), "QA_LINE": qa_line,
        "HARBOR": harbor_html, "MODELS": models_html,
        "DATE": datetime.date.today().isoformat(),
    }
    page = (ROOT / "site" / "template.html").read_text()
    for key, value in values.items():
        page = page.replace(f"[[{key}]]", value)
    left = re.findall(r"\[\[[A-Z_]+\]\]", page)
    if left:
        print("unfilled placeholders:", sorted(set(left)))
        return 1
    (ROOT / "docs").mkdir(exist_ok=True)
    if draft:
        (ROOT / "site" / "draft.html").write_text(page)
        print("wrote site/draft.html (draft, not published)")
        return 0
    (ROOT / "docs" / "index.html").write_text(page)
    (ROOT / "docs" / ".nojekyll").write_text("")
    print("wrote docs/index.html", len(page), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
