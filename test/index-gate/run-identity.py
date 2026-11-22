#!/usr/bin/env python3
"""publish-chart.yaml runs the index-gate action at a pinned commit; that commit's gate.sh must be main's gate.sh,
byte for byte. Otherwise the gate the index runs and the gate this repository tests (and release-oci pins) have
drifted apart, and a change to gate.sh would be tested here without ever reaching the publisher.

Reads the pin out of publish-chart.yaml and the pinned file with `git show <sha>:<path>`, so it needs the full
history (the workflow checks out with fetch-depth 0). It fails as VOID, distinctly, when the pin or the pinned
file cannot be found: a failed read must never read as agreement.
"""
import os, re, subprocess, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
PATH = ".github/actions/index-gate/gate.sh"
wf = open(os.path.join(ROOT, ".github", "workflows", "publish-chart.yaml")).read()
pins = re.findall(r"uses:\s*krateo-blueprints/charts/\.github/actions/index-gate@([0-9a-f]{40})", wf)
if len(pins) != 1:
    sys.exit(f"VOID: expected one pinned index-gate in publish-chart.yaml, found {len(pins)}")
sha = pins[0]
p = subprocess.run(["git", "-C", ROOT, "show", f"{sha}:{PATH}"], capture_output=True, text=True)
if p.returncode != 0 or not p.stdout:
    sys.exit(f"VOID: cannot read {PATH} at the pinned {sha} (is the history fetched?): {p.stderr.strip()}")
main = open(os.path.join(ROOT, PATH)).read()
if p.stdout != main:
    print(f"FAIL: publish-chart pins index-gate at {sha}, whose gate.sh differs from this commit's.")
    print("      Move the pin to a commit carrying this gate.sh (and its release), or revert the gate change.")
    sys.exit(1)
print(f"ok  publish-chart's pinned index-gate ({sha[:12]}) carries this commit's gate.sh")
