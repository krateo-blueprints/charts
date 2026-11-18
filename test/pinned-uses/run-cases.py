#!/usr/bin/env python3
"""Run pinned-uses.yaml's check step against generated workflow files and check each verdict.

The step's shell is read out of the workflow file itself, so this tests the bytes callers run. Each case
writes a .github/workflows/ directory into a temporary repository and runs the step there, the way the job
runs it in a caller's checkout.

Then the mutations. The script carries marked blocks: `sha-check`, `comment-check`, `inherit-check`,
`floating-check` (which accepts a recorded float) and, inside it, the four refusals `float-reason`, `float-sha`,
`float-publisher` and `float-branch`. Each is deleted in turn, and the cases that block exists for must flip
to the opposite verdict: a refused case to passing, an accepted float to refused. A case whose verdict a
mutant leaves unchanged is decided by something else, so it would prove nothing about that block, and this
fails.

One more mutant replaces `inherit-check` with the text search that misread the 44 krateo-blueprints callers
of release-notes.yaml on 2026-11-18: it counted every file containing `secrets: inherit`, including the
callers that pass secrets by name and quote `secrets: inherit` in the comment explaining why. The cases marked
`naive` must be refused by that mutant, so they are shown to test the difference between the key and a
mention of it.

Run from the repository root: python3 test/pinned-uses/run-cases.py
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml

WORKFLOW = ".github/workflows/pinned-uses.yaml"
STEP = "Every reusable workflow is pinned by commit SHA with a version comment, and gets no cross-org secrets inherit"
SHA = "788f1a6c106707ada89792f499afdcf3bc0b5d13"
RW = "krateo-blueprints/charts/.github/workflows/publish-chart.yaml"
CALLER = "krateo-blueprints/example"
# Another organisation's reusable, pinned correctly, so only the inherit check can refuse it.
XORG = "uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@%s # main 2026-11-17" % SHA
# The comment openstack-glance-operator-kog's caller carries above its named secrets, verbatim.
GLANCE_COMMENT = """    # EXPLICIT, NOT `inherit`. `secrets: inherit` carries nothing across an ORGANISATION
    # boundary, and this reusable lives in krateo-platformops while this repo does not. The
    # symptom was silent: HAVE_CRED evaluated false, the job skipped every step and still
    # reported success, so three orgs looked identical and only one was working. Named
    # passing reads this org's own secrets, which is what crosses.
"""
NAMED = """    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      RELEASE_FEED_TOKEN: ${{ secrets.RELEASE_FEED_TOKEN }}
"""


def job(uses_line):
    return "on: push\njobs:\n  x:\n    %s\n" % uses_line


def jobs(*bodies):
    # Each body is the job's key lines, already indented by four.
    return "on: push\njobs:\n" + "".join("  j%d:\n%s" % (i, b) for i, b in enumerate(bodies))


# (name, {file: text} or None for no workflows dir, passes?, text the output must contain, block it tests,
#  optionally a dict of extra options: caller, naive)
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
    ("cross-org inherit", {"a.yaml": jobs("    %s\n    secrets: inherit\n" % XORG)}, False, "inherit passes nothing across organisations", "inherit-check"),
    # openstack-keystone-operator-kog's caller line before #33, trailing comment and all.
    ("cross-org inherit, commented", {"a.yaml": jobs("    %s\n    permissions:\n      contents: write\n    secrets: inherit  # CLAUDE_CODE_OAUTH_TOKEN, and the optional Slack/feed credentials\n    with:\n      tag: x\n" % XORG)}, False, "a.yaml:7: `secrets: inherit`", "inherit-check"),
    ("cross-org inherit before uses", {"a.yaml": jobs("    secrets: inherit\n    %s\n" % XORG)}, False, "owned by krateo-platformops, not krateo-blueprints", "inherit-check"),
    ("cross-org inherit, quoted", {"a.yaml": jobs("    %s\n    secrets: \"inherit\"\n" % XORG)}, False, "1 cross-org secrets inherit", "inherit-check"),
    ("same-org inherit", {"a.yaml": jobs("    uses: %s@%s # 1.1.0\n    secrets: inherit\n" % (RW, SHA))}, True, "0 cross-org secrets inherit", None),
    ("same-org inherit, owner case", {"a.yaml": jobs("    uses: %s@%s # 1.1.0\n    secrets: inherit\n" % (RW, SHA))}, True, "0 cross-org secrets inherit", None, {"caller": "Krateo-Blueprints/example"}),
    ("cross-org named secrets", {"a.yaml": jobs("    %s\n%s" % (XORG, NAMED))}, True, "0 cross-org secrets inherit", None),
    # The 44-caller false positive: the fixed callers quote the key in the comment that explains the fix.
    ("cross-org, inherit only in comment", {"a.yaml": jobs("    %s\n%s%s" % (XORG, GLANCE_COMMENT, NAMED))}, True, "0 cross-org secrets inherit", None, {"naive": True}),
    ("cross-org, key commented out", {"a.yaml": jobs("    %s\n    # secrets: inherit\n%s" % (XORG, NAMED))}, True, "0 cross-org secrets inherit", None, {"naive": True}),
    # Job scoping: the inherit belongs to a same-org job; the cross-org job passes by name.
    ("inherit in a different job", {"a.yaml": jobs("    %s\n%s" % (XORG, NAMED), "    uses: %s@%s # 1.1.0\n    secrets: inherit\n" % (RW, SHA))}, True, "2 reusable-workflow uses, 0 not pinned (PUBLISHING.md rule 9), 0 cross-org", None, {"naive": True}),
    # A `secrets:` key of a nested mapping is not the job's.
    ("inherit under with:", {"a.yaml": jobs("    %s\n    with:\n      secrets: inherit\n%s" % (XORG, NAMED))}, True, "0 cross-org secrets inherit", None, {"naive": True}),
    ("caller unknown", {"a.yaml": jobs("    %s\n%s" % (XORG, NAMED))}, False, "CALLER (github.repository) is empty", None, {"caller": ""}),
]

# A deliberate float (PUBLISHING.md rule 9): a branch ref with `# floating: <reason>`.
XFLOAT = "uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@%s # floating: %s"
REASON = "follows the org reusable at main, decided for nova-kog 2026-11-07"

CASES += [
    ("float a branch, with reason", {"a.yaml": job(XFLOAT % ("main", REASON))}, True,
     "a.yaml:4: krateo-platformops/.github/.github/workflows/release-notes.yaml@main floats, reason: " + REASON, "floating-check"),
    ("float a non-main branch", {"a.yaml": job(XFLOAT % ("release-2026", "staging the next cut"))}, True,
     "0 not pinned (PUBLISHING.md rule 9), 0 cross-org secrets inherit, 1 floating", "floating-check"),
    ("float, quoted target", {"a.yaml": job('uses: "krateo-platformops/.github/.github/workflows/security.yml@main" # floating: ' + REASON)}, True,
     "1 floating", "floating-check"),
    ("float among pins", {"a.yaml": job("uses: %s@%s # 1.1.0" % (RW, SHA)), "b.yaml": job(XFLOAT % ("main", REASON))}, True,
     "2 reusable-workflow uses, 0 not pinned (PUBLISHING.md rule 9), 0 cross-org secrets inherit, 1 floating", None),
    ("float, empty reason", {"a.yaml": job("uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@main # floating:")}, False,
     "with an empty reason", "float-reason"),
    ("float, blank reason", {"a.yaml": job("uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@main # floating:    ")}, False,
     "with an empty reason", "float-reason"),
    ("float on a SHA pin", {"a.yaml": job(XFLOAT % (SHA, REASON))}, False,
     "which is meaningless", "float-sha"),
    ("float the publisher", {"a.yaml": job("uses: %s@main # floating: %s" % (RW, REASON))}, False,
     "floats the publisher", "float-publisher"),
    ("float the publisher, case", {"a.yaml": job("uses: Krateo-Blueprints/charts/.github/workflows/publish-chart.yaml@main # floating: " + REASON)}, False,
     "floats the publisher", "float-publisher"),
    ("float a tag", {"a.yaml": job(XFLOAT % ("1.1.0", REASON))}, False, "not a branch", "float-branch"),
    ("float a v-tag", {"a.yaml": job(XFLOAT % ("v1", REASON))}, False, "not a branch", "float-branch"),
    ("float an abbreviated sha", {"a.yaml": job(XFLOAT % ("788f1a6", REASON))}, False, "not a branch", "float-branch"),
    # Not the exemption's syntax: the colon is required, so this is an unpinned branch.
    ("floating without colon", {"a.yaml": job("uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@main # floating " + REASON)}, False,
     "a deliberate float of a branch says `# floating: <reason>`", None),
    # A float does not excuse the cross-org inherit.
    ("float with cross-org inherit", {"a.yaml": jobs("    %s\n    secrets: inherit\n" % (XFLOAT % ("main", REASON)))}, False,
     "0 not pinned (PUBLISHING.md rule 9), 1 cross-org secrets inherit, 1 floating", "inherit-check"),
]

NAIVE_BODY = """owner = target.split("/", 1)[0].lower()
if owner != caller_owner and "secrets: inherit" in "\\n".join(lines):
    inherits.append("%s: naive text search found secrets: inherit" % where)"""


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


def replaced(script, block, body):
    lines = script.split("\n")
    b = [i for i, l in enumerate(lines) if "# BEGIN %s" % block in l]
    e = [i for i, l in enumerate(lines) if "# END %s" % block in l]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        sys.exit("FAIL: block %r is not marked exactly once in the step; the mutation cannot be made" % block)
    pad = lines[b[0]][:len(lines[b[0]]) - len(lines[b[0]].lstrip(" "))]
    return "\n".join(lines[:b[0]] + [pad + l for l in body.split("\n")] + lines[e[0] + 1:])


def opts(case):
    return case[5] if len(case) > 5 else {}


def run(script, files, caller=CALLER):
    with tempfile.TemporaryDirectory() as repo:
        if files is not None:
            wf = os.path.join(repo, ".github", "workflows")
            os.makedirs(wf)
            for name, text in files.items():
                open(os.path.join(wf, name), "w").write(text)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(script)
        env = dict(os.environ, WORKDIR=repo, CALLER=caller)
        p = subprocess.run(["bash", f.name], env=env, capture_output=True, text=True)
        os.unlink(f.name)
        return p.returncode == 0, p.stdout + p.stderr


def main():
    script = step_script()
    failures = 0
    for case in CASES:
        name, files, want_ok, want_text = case[:4]
        ok, out = run(script, files, opts(case).get("caller", CALLER))
        good = ok == want_ok and want_text in out
        failures += not good
        print("%s  %-30s exit=%s  (want %s, %r)" % ("ok  " if good else "FAIL", name, "0" if ok else "1",
                                                     "success" if want_ok else "failure", want_text))
        if not good:
            print("      output: " + out.strip().replace("\n", "\n              "))
    blocks = ("sha-check", "comment-check", "inherit-check", "floating-check",
              "float-reason", "float-sha", "float-publisher", "float-branch")
    for block in blocks:
        mutant = without(script, block)
        for case in CASES:
            name, files, want_ok, _, tests = case[:5]
            if tests != block or name == "one bad among good":
                continue
            ok, out = run(mutant, files, opts(case).get("caller", CALLER))
            good = ok != want_ok
            failures += not good
            print("%s  without %-15s %-30s %s" % ("ok  " if good else "FAIL", block, name,
                                                  "verdict flips, so the case tests this block" if good else
                                                  "VERDICT UNCHANGED: the case does not test this block"))
    # Every block is tested by at least one case: a block no case names is checked by nothing.
    for block in blocks:
        if not any(len(c) > 4 and c[4] == block for c in CASES):
            failures += 1
            print("FAIL  block %s has no case that tests it" % block)
    naive = replaced(script, "inherit-check", NAIVE_BODY)
    for case in CASES:
        if not opts(case).get("naive"):
            continue
        ok, out = run(naive, case[1], opts(case).get("caller", CALLER))
        good = not ok and "naive text search" in out
        failures += not good
        print("%s  naive search  %-30s %s" % ("ok  " if good else "FAIL", case[0],
                                              "refused, so the case tells the key from a mention" if good else
                                              "NOT REFUSED: the case does not exercise the difference"))
    print("%d case(s) and their mutants, %d failure(s)" % (len(CASES), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
