#!/usr/bin/env python3
"""index-gate's gate.sh is publish-chart.yaml's "Content gate" step, byte for byte but for the directory
parameter, while publish-chart still carries the step inline. This holds the two together until publish-chart
calls the action (then this test is replaced by one comparing publish-chart's pinned gate.sh with main's).
"""
import os, sys, yaml

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "publish-chart.yaml")))
runs = [s["run"] for s in wf["jobs"]["publish"]["steps"] if str(s.get("name", "")).startswith("Content gate")]
if len(runs) != 1:
    sys.exit(f"VOID: expected one 'Content gate' step in publish-chart.yaml, found {len(runs)}")
step = runs[0]
if not step.startswith("set -euo pipefail\n"):
    sys.exit("VOID: the Content gate step no longer starts with set -euo pipefail; re-derive the comparison")
step_body = step[len("set -euo pipefail\n"):].replace("for tgz in dist/*.tgz; do", 'for tgz in "${DIST}"/*.tgz; do')
gate = open(os.path.join(ROOT, ".github", "actions", "index-gate", "gate.sh")).read()
marker = ': "${SRC:?SRC is required (<owner>/<repo>)}"\n'
if gate.count(marker) != 1:
    sys.exit("VOID: gate.sh's header marker is not found exactly once; re-derive the comparison")
gate_body = gate.split(marker, 1)[1]
if gate_body != step_body:
    import difflib
    print("FAIL: gate.sh differs from publish-chart.yaml's Content gate step:")
    sys.stdout.writelines(difflib.unified_diff(step_body.splitlines(True), gate_body.splitlines(True), "publish-chart step", "gate.sh"))
    sys.exit(1)
print(f"ok  gate.sh is publish-chart's Content gate step ({len(gate_body.splitlines())} lines), but for the directory parameter")
