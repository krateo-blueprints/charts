#!/usr/bin/env python3
"""Run release-preflight.yaml's hook step against every fixture and check its exit code.

The step's shell is read out of the workflow file itself, so this tests the bytes callers run, not a
copy that could drift from them. A failing case cannot be shown as a failing job without turning this
repository's own CI red, so the refusal semantics are tested here, on the step, and the wiring (a call
through `uses:`, and `needs:` gating the job after it) by the passing calls in
test-release-preflight.yaml.

Run from the repository root: python3 test/release-preflight/run-cases.py
"""
import os
import subprocess
import sys
import tempfile

import yaml

WORKFLOW = ".github/workflows/release-preflight.yaml"
STEP = "Run hack/release-preflight"
FIX = "test/release-preflight"

# (fixture dir, version, expect success?, text the output must contain)
CASES = [
    ("absent", "9.8.7", True, "declares no release preflight"),
    ("passes", "9.8.7", True, "fixture: preflight ok for 9.8.7"),
    ("passes", "1.2.3", False, "expected version 9.8.7"),       # the version really arrives as $1
    ("passes", "", False, "empty version"),
    ("fails", "9.8.7", False, "fixture: refusing release 9.8.7"),
    ("not-executable", "9.8.7", False, "is not executable"),
    ("dangling", "9.8.7", False, "is not a regular file"),
]


def step_script():
    wf = yaml.safe_load(open(WORKFLOW))
    steps = wf["jobs"]["preflight"]["steps"]
    matches = [s for s in steps if s.get("name") == STEP]
    if len(matches) != 1:
        sys.exit("FAIL: expected exactly one step named %r in %s, found %d" % (STEP, WORKFLOW, len(matches)))
    return matches[0]["run"]


def main():
    script = step_script()
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    failures = 0
    for fixture, version, want_ok, want_text in CASES:
        env = dict(os.environ, VERSION=version, WORKDIR=os.path.join(FIX, fixture))
        p = subprocess.run(["bash", path], env=env, capture_output=True, text=True)
        out = p.stdout + p.stderr
        ok = (p.returncode == 0) == want_ok and want_text in out
        failures += not ok
        print("%s  %-15s version=%-6r exit=%d  (want %s, %r)"
              % ("ok  " if ok else "FAIL", fixture, version, p.returncode,
                 "success" if want_ok else "failure", want_text))
        if not ok:
            print("      output: " + out.strip().replace("\n", "\n              "))
    os.unlink(path)
    print("%d case(s), %d failure(s)" % (len(CASES), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
