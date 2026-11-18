#!/usr/bin/env python3
"""Run pinned-uses.yaml's check step against generated workflow files and check each verdict.

The step's shell is read out of the workflow file itself, so this tests the bytes callers run. Each case
writes a .github/workflows/ directory into a temporary repository and runs the step there, the way the job
runs it in a caller's checkout.

Then the mutations. The script carries two marked blocks: `sha-check` and `comment-check`. Each is deleted
in turn, and the cases that block exists for must flip to passing. A case that a mutant still refuses is
refused by something else, so it would prove nothing about that block, and this fails.

Run from the repository root: python3 test/pinned-uses/run-cases.py
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml

WORKFLOW = ".github/workflows/pinned-uses.yaml"
STEP = "Every reusable workflow is pinned by commit SHA with a version comment"
SHA = "788f1a6c106707ada89792f499afdcf3bc0b5d13"
RW = "krateo-blueprints/charts/.github/workflows/publish-chart.yaml"


def job(uses_line):
    return "on: push\njobs:\n  x:\n    %s\n" % uses_line


# (name, {file: text} or None for no workflows dir, passes?, text the output must contain, block it tests)
CASES = [
    ("pinned to a tag's commit", {"a.yaml": job("uses: %s@%s # 1.1.0" % (RW, SHA))}, True, "1 reusable-workflow uses, 0 not pinned", None),
    ("pinned, untagged repo, dated", {"a.yml": job("uses: krateo-platformops/.github/.github/workflows/security.yml@%s # main 2026-11-17" % SHA)}, True, "0 not pinned", None),
    ("quoted target", {"a.yaml": job('uses: "%s@%s" # 1.1.0' % (RW, SHA))}, True, "0 not pinned", None),
    ("local workflow, any ref", {"a.yaml": job("uses: ./.github/workflows/b.yaml")}, True, "0 reusable-workflow uses", None),
    ("action, out of scope", {"a.yaml": "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v7\n"}, True, "0 reusable-workflow uses", None),
    ("branch ref", {"a.yaml": job("uses: %s@main # 1.1.0" % RW)}, False, "not a 40-hex commit SHA", "sha-check"),
    ("tag ref", {"a.yaml": job("uses: %s@1.1.0 # 1.1.0" % RW)}, False, "not a 40-hex commit SHA", "sha-check"),
    ("abbreviated sha", {"a.yaml": job("uses: %s@788f1a6 # 1.1.0" % RW)}, False, "not a 40-hex commit SHA", "sha-check"),
    ("sha, no comment", {"a.yaml": job("uses: %s@%s" % (RW, SHA))}, False, "needs `# X.Y.Z`", "comment-check"),
    ("sha, comment not a version", {"a.yaml": job("uses: %s@%s # latest" % (RW, SHA))}, False, "needs `# X.Y.Z`", "comment-check"),
    ("one bad among good", {"a.yaml": job("uses: %s@%s # 1.1.0" % (RW, SHA)), "b.yaml": job("uses: %s@main" % RW)}, False, "2 reusable-workflow uses, 1 not pinned", "sha-check"),
    ("no workflow files", None, False, "nothing was checked", None),
]


def step_script():
    wf = yaml.safe_load(open(WORKFLOW))
    steps = wf["jobs"]["pinned-uses"]["steps"]
    matches = [s for s in steps if s.get("name") == STEP]
    if len(matches) != 1:
        sys.exit("FAIL: expected exactly one step named %r in %s, found %d" % (STEP, WORKFLOW, len(matches)))
    return matches[0]["run"]


def without(script, block):
    lines = script.split("\n")
    b = [i for i, l in enumerate(lines) if "# BEGIN %s" % block in l]
    e = [i for i, l in enumerate(lines) if "# END %s" % block in l]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        sys.exit("FAIL: block %r is not marked exactly once in the step; the mutation cannot be made" % block)
    return "\n".join(lines[:b[0]] + lines[e[0] + 1:])


def run(script, files):
    with tempfile.TemporaryDirectory() as repo:
        if files is not None:
            wf = os.path.join(repo, ".github", "workflows")
            os.makedirs(wf)
            for name, text in files.items():
                open(os.path.join(wf, name), "w").write(text)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(script)
        env = dict(os.environ, WORKDIR=repo)
        p = subprocess.run(["bash", f.name], env=env, capture_output=True, text=True)
        os.unlink(f.name)
        return p.returncode == 0, p.stdout + p.stderr


def main():
    script = step_script()
    failures = 0
    for name, files, want_ok, want_text, _ in CASES:
        ok, out = run(script, files)
        good = ok == want_ok and want_text in out
        failures += not good
        print("%s  %-30s exit=%s  (want %s, %r)" % ("ok  " if good else "FAIL", name, "0" if ok else "1",
                                                     "success" if want_ok else "failure", want_text))
        if not good:
            print("      output: " + out.strip().replace("\n", "\n              "))
    for block in ("sha-check", "comment-check"):
        mutant = without(script, block)
        for name, files, want_ok, _, tests in CASES:
            if tests != block or name == "one bad among good":
                continue
            ok, out = run(mutant, files)
            good = ok
            failures += not good
            print("%s  without %-13s %-30s %s" % ("ok  " if good else "FAIL", block, name,
                                                  "passes, so the case tests this block" if good else
                                                  "STILL REFUSED: the case does not test this block"))
    print("%d case(s) and their mutants, %d failure(s)" % (len(CASES), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
