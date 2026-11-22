#!/usr/bin/env python3
r"""Run release-preflight.yaml's hook step against every fixture and check its exit code.

The step's shell is read out of the workflow file itself, so this tests the bytes callers run, not a
copy that could drift from them. A failing case cannot be shown as a failing job without turning this
repository's own CI red, so the refusal semantics are tested here, on the step, and the wiring (a call
through `uses:`, and `needs:` gating the job after it) by the passing calls in
test-release-preflight.yaml.

Rule 13 before any push: the version is checked against the plain X.Y.Z pattern before the hook runs.
The RULE13 cases run on the `absent` fixture, so only that check can refuse them. Then two mutants, each
of which every refused RULE13 case must notice:
  - the check deleted;
  - the pattern loosened to `^[0-9]+\.[0-9]+\.[0-9]+$`, github-provider-kog#111's own check, which
    accepted 0.015.0.
Last, the pattern must be byte-identical to the one publish-chart.yaml refuses at index time, so the
two cannot drift.

Run from the repository root: python3 test/release-preflight/run-cases.py
"""
import re
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

# Rule 13, on the fixture without a hook: only the version check decides. (version, plain?)
RULE13 = [
    ("1.2.3", True), ("0.0.0", True), ("10.20.30", True), ("0.15.0", True),
    ("0.015.0", False),          # leading zero: github-provider-kog#111's check accepted it
    ("01.2.3", False), ("1.02.3", False),
    ("v1.2.3", False), ("1.2.3-rc.1", False), ("1.2.3-main.gabc1234", False), ("1.2.3+build.5", False),
    ("1.2", False), ("1.2.3.4", False), (" 1.2.3", False), ("1.2.3 ", False), ("x.y.z", False),
]
LOOSE = "PLAIN_VERSION='^[0-9]+\\.[0-9]+\\.[0-9]+$'"
PATTERN = re.compile(r"^\s*PLAIN_VERSION='([^']*)'\s*$", re.M)


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
    # The dangling-link fixture is built here, not committed: this repository hosts actions (index-gate),
    # and a caller's runner unpacks the whole repository archive at the pinned commit to run one. A
    # committed dangling symlink failed that unpacking ("Could not find file ...") for every caller of
    # release-oci 2.0.0, before any step ran. test-repository-archive.yaml refuses any tracked symlink.
    dangling = tempfile.mkdtemp()
    os.makedirs(os.path.join(dangling, "hack"))
    os.symlink("does-not-exist", os.path.join(dangling, "hack", "release-preflight"))
    for fixture, version, want_ok, want_text in CASES:
        workdir = dangling if fixture == "dangling" else os.path.join(FIX, fixture)
        env = dict(os.environ, VERSION=version, WORKDIR=workdir)
        p = subprocess.run(["bash", path], env=env, capture_output=True, text=True)
        out = p.stdout + p.stderr
        ok = (p.returncode == 0) == want_ok and want_text in out
        failures += not ok
        print("%s  %-15s version=%-6r exit=%d  (want %s, %r)"
              % ("ok  " if ok else "FAIL", fixture, version, p.returncode,
                 "success" if want_ok else "failure", want_text))
        if not ok:
            print("      output: " + out.strip().replace("\n", "\n              "))
    def run13(script_text, version):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as g:
            g.write(script_text)
        env = dict(os.environ, VERSION=version, WORKDIR=os.path.join(FIX, "absent"))
        p = subprocess.run(["bash", g.name], env=env, capture_output=True, text=True)
        os.unlink(g.name)
        return p.returncode == 0, p.stdout + p.stderr

    for version, plain in RULE13:
        ok, out = run13(script, version)
        good = ok == plain and (plain or "is not a plain X.Y.Z" in out)
        failures += not good
        print("%s  rule 13   version=%-22r exit=%d  (want %s)" % ("ok  " if good else "FAIL", version, 0 if ok else 1,
                                                                  "success" if plain else "refusal"))
        if not good:
            print("      output: " + out.strip().replace("\n", "\n              "))
    lines = script.split("\n")
    b = [i for i, l in enumerate(lines) if "# BEGIN rule-13 preflight check" in l]
    e = [i for i, l in enumerate(lines) if "# END rule-13 preflight check" in l]
    m = PATTERN.findall(script)
    if len(b) != 1 or len(e) != 1 or len(m) != 1:
        failures += 1
        print("FAIL  the rule-13 block or its PLAIN_VERSION is not marked exactly once; the mutants cannot be made")
    else:
        mutants = [("check deleted", "\n".join(lines[:b[0]] + lines[e[0] + 1:])),
                   ("pattern loosened (github-provider-kog#111)", PATTERN.sub(lambda _m: "          " + LOOSE, script, count=1))]
        for label, mutant in mutants:
            caught = [v for v, plain in RULE13 if not plain and run13(mutant, v)[0] is True]
            good = bool(caught)
            failures += not good
            print("%s  mutant %-44s %s" % ("ok  " if good else "FAIL", label,
                                          "caught by %s" % ", ".join(caught) if good else "NOT CAUGHT by any case"))
        # One definition: the pattern publish-chart.yaml refuses at index time is this one, byte for byte.
        pub = PATTERN.findall(open(".github/actions/index-gate/gate.sh").read())
        same = len(pub) == 1 and pub[0] == m[0]
        failures += not same
        print("%s  pattern identical to the index gate's, gate.sh (%s)" % ("ok  " if same else "FAIL", pub if not same else m[0]))
    os.unlink(path)
    print("%d case(s), %d rule-13 case(s), %d failure(s)" % (len(CASES), len(RULE13), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
