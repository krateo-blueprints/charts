#!/usr/bin/env python3
"""Run pinned-uses.yaml's check step against generated workflow files and check each verdict.

The step's shell is read out of the workflow file itself, so this tests the bytes callers run. Each case
writes a .github/workflows/ directory into a temporary repository and runs the step there, the way the job
runs it in a caller's checkout.

Then the mutations. The script carries marked blocks: `sha-check`, `comment-check` and, inside it,
`float-form` (the float as a first-class comment form), `inherit-check`, `float-accept` (which accepts a
recorded float) and, inside it, the refusals `float-date`, `float-reason`, `float-owner`, `float-publisher`,
`float-sha` and `float-branch`; and for rule 14, `action-scope` (the shared chart-push action is checked),
`action-sha`, `action-comment`, `bare-push` and `push-comment` (a commented line is not a push). Each is deleted in turn, and the cases that block exists for must flip to the
opposite verdict: a refused case to passing, an accepted float to refused. Where a case names the reason the
mutant must be caught for (`mutant_text`), the mutant's output must say it. A case whose verdict a mutant
leaves unchanged is decided by something else, so it would prove nothing about that block, and this fails.
Every block must have at least one case.

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
STEP = "Every reusable workflow and shared action is pinned by commit SHA with a version comment, no cross-org secrets inherit, no bare chart push"
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
    ("inherit in a different job", {"a.yaml": jobs("    %s\n%s" % (XORG, NAMED), "    uses: %s@%s # 1.1.0\n    secrets: inherit\n" % (RW, SHA))}, True, "2 reusable-workflow uses, 0 not pinned (PUBLISHING.md rule 9), 0 floating, 0 cross-org secrets inherit", None, {"naive": True}),
    # A `secrets:` key of a nested mapping is not the job's.
    ("inherit under with:", {"a.yaml": jobs("    %s\n    with:\n      secrets: inherit\n%s" % (XORG, NAMED))}, True, "0 cross-org secrets inherit", None, {"naive": True}),
    ("caller unknown", {"a.yaml": jobs("    %s\n%s" % (XORG, NAMED))}, False, "CALLER (github.repository) is empty", None, {"caller": ""}),
]

# A deliberate float (PUBLISHING.md rule 9): a branch ref with `# floating: YYYY-MM-DD <reason>`.
PF = "krateo-platformops/.github/.github/workflows/release-notes.yaml"
DATE = "2026-11-07"
REASON = "follows the org reusable at main, decided for nova-kog"


def fl(target, ref, comment):
    return job("uses: %s@%s # %s" % (target, ref, comment))


def fl_block(block_lines, comment, blank=False):
    # A job whose `uses:` carries the marker alone, with a comment block above it.
    body = "".join("    # %s\n" % l if l else "    #\n" for l in block_lines)
    return "on: push\njobs:\n  x:\n%s%s    uses: %s@main # %s\n" % (body, "\n" if blank else "", PF, comment)


FORMAT_ERR = "needs `# X.Y.Z`"
CASES += [
    # accepted
    ("float inline reason", {"a.yaml": fl(PF, "main", "floating: %s %s" % (DATE, REASON))}, True,
     "a.yaml:4: %s@main floats since %s, reason: %s" % (PF, DATE, REASON), "float-accept"),
    # The float is a first-class comment form: no format error, and dropping the form is caught as one.
    ("float is no comment-format error", {"a.yaml": fl(PF, "main", "floating: %s %s" % (DATE, REASON))}, True,
     "0 not pinned", "float-form", {"absent": FORMAT_ERR, "mutant_text": FORMAT_ERR}),
    ("float reason in block above", {"a.yaml": fl_block(["NOVA FLOATS THE ORG WORKFLOWS.", "Decided 2026-11-07, reaffirmed 2026-11-18;", "the publisher stays pinned."], "floating: " + DATE)}, True,
     "floats since 2026-11-07, reason: NOVA FLOATS THE ORG WORKFLOWS. Decided 2026-11-07, reaffirmed 2026-11-18; the publisher stays pinned.", "float-accept"),
    ("float non-main branch, blueprints", {"a.yaml": fl("krateo-blueprints/charts/.github/workflows/release-preflight.yaml", "release-2026", "floating: 2026-11-18 staging the next cut")}, True,
     "0 not pinned (PUBLISHING.md rule 9), 1 floating, 0 cross-org secrets inherit", "float-accept"),
    ("float, quoted target", {"a.yaml": job('uses: "krateo-platformops/.github/.github/workflows/security.yml@main" # floating: %s %s' % (DATE, REASON))}, True,
     "1 floating", "float-accept"),
    ("float among pins", {"a.yaml": job("uses: %s@%s # 1.1.0" % (RW, SHA)), "b.yaml": fl(PF, "main", "floating: %s %s" % (DATE, REASON))}, True,
     "2 reusable-workflow uses, 0 not pinned (PUBLISHING.md rule 9), 1 floating, 0 cross-org secrets inherit", None),
    # refused: the date
    ("float, no date", {"a.yaml": fl(PF, "main", "floating: " + REASON)}, False, "where the date belongs", "float-date"),
    ("float, impossible date", {"a.yaml": fl(PF, "main", "floating: 2026-13-45 " + REASON)}, False, "'2026-13-45' where the date belongs", "float-date"),
    ("float, date not ISO", {"a.yaml": fl(PF, "main", "floating: 07/11/2026 " + REASON)}, False, "where the date belongs", "float-date"),
    ("float, marker only", {"a.yaml": fl(PF, "main", "floating:")}, False, "where the date belongs", None),
    # refused: the reason
    ("float, date only, no block", {"a.yaml": fl(PF, "main", "floating: " + DATE)}, False, "floats with no reason", "float-reason"),
    ("float, block of bare #", {"a.yaml": fl_block(["", ""], "floating: " + DATE)}, False, "floats with no reason", "float-reason"),
    ("float, blank line before uses", {"a.yaml": fl_block(["a reason, but detached"], "floating: " + DATE, blank=True)}, False, "floats with no reason", "float-reason"),
    # A comment above the job header belongs to no job.
    ("float, block outside the job", {"a.yaml": "on: push\njobs:\n  # a reason outside the job\n  x:\n    uses: %s@main # floating: %s\n" % (PF, DATE)}, False, "floats with no reason", "float-reason"),
    # refused: what the gate can verify about the target
    ("float, foreign owner", {"a.yaml": fl("octo-org/shared/.github/workflows/x.yaml", "main", "floating: %s %s" % (DATE, REASON))}, False,
     "floats a reusable owned by octo-org", "float-owner"),
    ("float the publisher", {"a.yaml": fl(RW, "main", "floating: %s %s" % (DATE, REASON))}, False, "floats the publisher", "float-publisher"),
    ("float the publisher, case", {"a.yaml": fl("Krateo-Blueprints/charts/.github/workflows/publish-chart.yaml", "main", "floating: %s %s" % (DATE, REASON))}, False,
     "floats the publisher", "float-publisher"),
    ("float on a SHA pin", {"a.yaml": fl(PF, SHA, "floating: %s %s" % (DATE, REASON))}, False, "which is meaningless", "float-sha"),
    ("float a tag", {"a.yaml": fl(PF, "1.1.0", "floating: %s %s" % (DATE, REASON))}, False, "not a branch", "float-branch"),
    ("float a v-tag", {"a.yaml": fl(PF, "v1", "floating: %s %s" % (DATE, REASON))}, False, "not a branch", "float-branch"),
    ("float an abbreviated sha", {"a.yaml": fl(PF, "788f1a6", "floating: %s %s" % (DATE, REASON))}, False, "not a branch", "float-branch"),
    # Not the exemption's syntax: the colon is required.
    ("floating without colon", {"a.yaml": fl(PF, "main", "floating %s %s" % (DATE, REASON))}, False,
     "or a recorded float `# floating: YYYY-MM-DD <reason>`", None),
    # A float does not excuse the cross-org inherit.
    ("float with cross-org inherit", {"a.yaml": jobs("    uses: %s@main # floating: %s %s\n    secrets: inherit\n" % (PF, DATE, REASON))}, False,
     "0 not pinned (PUBLISHING.md rule 9), 1 floating, 1 cross-org secrets inherit", "inherit-check"),
]

# PUBLISHING.md rule 14: the shared chart-push action is pinned like a reusable (`# X.Y.Z`, or `# main YYYY-MM-DD` while
# krateo-platformops/.github is untagged), never floated, and no workflow pushes a chart bare.
ACT = "krateo-platformops/.github/.github/actions/chart-push"


def steps(*lines):
    # A job whose steps are the given lines, each already a full step line without indentation.
    return "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n" + "".join("      %s\n" % l for l in lines)


def run_block(*body):
    # One step whose `run: |` block holds the given shell lines.
    return steps("- name: release", "  run: |") .replace("  run: |\n", "  run: |\n" + "".join("          %s\n" % l for l in body))


ACT_USE = "- uses: %s@%s # main 2026-11-18" % (ACT, SHA)
PUSH_ERR = "push charts through krateo-platformops/.github/.github/actions/chart-push"
CASES += [
    # the shared action is in scope, pinned like a reusable: dated while its repository is untagged, or a tag
    ("shared action pinned, dated", {"a.yaml": steps(ACT_USE, "  with:", "    chart: dist/demo-0.1.0.tgz")}, True,
     "0 reusable-workflow uses, 0 not pinned (PUBLISHING.md rule 9), 0 floating, 0 cross-org secrets inherit, 1 shared-action uses, 0 bare chart push(es)", None),
    ("shared action pinned, tagged", {"a.yaml": steps("- uses: %s@%s # 1.0.0" % (ACT, SHA))}, True, "1 shared-action uses, 0 bare", None),
    ("shared action, quoted", {"a.yaml": steps('- uses: "%s@%s" # main 2026-11-18' % (ACT, SHA))}, True, "1 shared-action uses", None),
    # release-oci.yaml's call today: refused by the ref and by the missing comment, so neither deletion alone flips it.
    ("shared action at main, as release-oci", {"a.yaml": steps("- uses: %s@main" % ACT)}, False,
     "not a 40-hex commit SHA; the shared chart-push action is always pinned by commit", None),
    ("shared action at main, dated comment", {"a.yaml": steps("- uses: %s@main # main 2026-11-17" % ACT)}, False,
     "not a 40-hex commit SHA; the shared chart-push action is always pinned by commit", "action-sha"),
    ("shared action tag ref", {"a.yaml": steps("- uses: %s@1.0.0 # 1.0.0" % ACT)}, False, "is pinned to '1.0.0'", "action-sha"),
    ("shared action abbreviated sha", {"a.yaml": steps("- uses: %s@f25d6b5 # main 2026-11-17" % ACT)}, False, "1 shared-action uses", "action-scope"),
    ("shared action, owner case", {"a.yaml": steps("- uses: Krateo-Platformops/.GitHub/.github/actions/chart-push@main # main 2026-11-17")}, False,
     "1 not pinned", "action-scope"),
    ("shared action, no comment", {"a.yaml": steps("- uses: %s@%s" % (ACT, SHA))}, False, "needs `# X.Y.Z`, or `# main YYYY-MM-DD`", "action-comment"),
    ("shared action, comment not a version", {"a.yaml": steps("- uses: %s@%s # latest" % (ACT, SHA))}, False,
     "has comment 'latest'", "action-comment"),
    ("shared action, float on a sha", {"a.yaml": steps("- uses: %s@%s # floating: 2026-11-18 follow main" % (ACT, SHA))}, False,
     "and is never floated", "action-comment"),
    # Refused by both the ref and the comment, so neither deletion alone flips it.
    ("shared action floated", {"a.yaml": steps("- uses: %s@main # floating: 2026-11-18 follow main" % ACT)}, False,
     "never floated (PUBLISHING.md rule 14)", None),
    # Out of scope: another action of the same repository, a name that only starts the same, another owner's.
    ("same repo, another action", {"a.yaml": steps("- uses: krateo-platformops/.github/.github/actions/chart-version-guard@main")}, True,
     "0 shared-action uses", None),
    ("a longer name, out of scope", {"a.yaml": steps("- uses: krateo-platformops/.github/.github/actions/chart-push-extra@main")}, True,
     "0 shared-action uses", None),
    ("another org action, out of scope", {"a.yaml": steps("- uses: krateo-blueprints/actions/.github/actions/chart-push@main")}, True,
     "0 shared-action uses", None),
    # bare pushes
    ("bare helm push, run line", {"a.yaml": steps("- run: helm push dist/demo-0.1.0.tgz oci://ghcr.io/krateo-blueprints/charts")}, False,
     "a.yaml:6: a bare `helm push`; " + PUSH_ERR, "bare-push"),
    ("bare helm push, in a loop", {"a.yaml": run_block("for f in dist/*.tgz; do", '  helm push "$f" oci://ghcr.io/krateo-blueprints/charts', "done")}, False,
     "1 bare chart push(es)", "bare-push"),
    ("bare helm push after &&", {"a.yaml": run_block("helm package charts/demo -d dist && helm push dist/*.tgz oci://ghcr.io/krateo-blueprints/charts")}, False,
     "a bare `helm push`", "bare-push"),
    ("bare helm push, extra spaces", {"a.yaml": run_block("helm  push dist/demo-0.1.0.tgz oci://ghcr.io/krateo-blueprints/charts")}, False,
     "a bare `helm push`", "bare-push"),
    ("bare oras push", {"a.yaml": run_block("oras push ghcr.io/krateo-blueprints/charts/demo:0.1.0 demo-0.1.0.tgz")}, False,
     "a bare `oras push`", "bare-push"),
    ("bare push among clean files", {"a.yaml": steps(ACT_USE), "b.yml": run_block("helm push x.tgz oci://r/p")}, False,
     "1 shared-action uses, 1 bare chart push(es)", "bare-push"),
    # a pinned reusable does not excuse a bare push in the same file
    ("bare push beside a good pin", {"a.yaml": job("uses: %s@%s # 1.1.0" % (RW, SHA)) + "  y:\n    runs-on: ubuntu-latest\n    steps:\n      - run: helm push x.tgz oci://r/p\n"}, False,
     "0 not pinned (PUBLISHING.md rule 9), 0 floating, 0 cross-org secrets inherit, 0 shared-action uses, 1 bare chart push(es)", "bare-push"),
    # commented pushes are not pushes
    ("commented helm push, YAML", {"a.yaml": steps("# - run: helm push dist/demo-0.1.0.tgz oci://ghcr.io/krateo-blueprints/charts", ACT_USE)}, True,
     "0 bare chart push(es)", "push-comment"),
    ("commented helm push, shell", {"a.yaml": run_block("# was: helm push \"$f\" oci://ghcr.io/krateo-blueprints/charts", "echo done")}, True,
     "0 bare chart push(es)", "push-comment"),
    ("commented oras push", {"a.yaml": run_block("  # oras push ghcr.io/x/y:1 a.tgz", "true")}, True, "0 bare chart push(es)", "push-comment"),
    # not a push
    ("helm package and pull", {"a.yaml": run_block("helm package charts/demo -d dist", "helm pull oci://ghcr.io/krateo-blueprints/charts/demo --version 0.1.0")}, True,
     "0 bare chart push(es)", None),
    ("helm-push as part of a word", {"a.yaml": run_block("helm cm-push dist/demo.tgz museum", "echo myhelm push-it", "echo helm pushes")}, True,
     "0 bare chart push(es)", None),
    ("push through the action", {"a.yaml": steps("- name: Push the chart", "  id: push", "  uses: %s@%s # main 2026-11-18" % (ACT, SHA), "  with:", "    chart: dist/demo-0.1.0.tgz", "    repository: oci://ghcr.io/krateo-blueprints/charts")}, True,
     "1 shared-action uses, 0 bare chart push(es)", None),
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
        absent = opts(case).get("absent")
        good = ok == want_ok and want_text in out and not (absent and absent in out)
        failures += not good
        print("%s  %-30s exit=%s  (want %s, %r)" % ("ok  " if good else "FAIL", name, "0" if ok else "1",
                                                     "success" if want_ok else "failure", want_text))
        if not good:
            print("      output: " + out.strip().replace("\n", "\n              "))
    blocks = ("sha-check", "comment-check", "float-form", "inherit-check", "float-accept",
              "float-date", "float-reason", "float-owner", "float-publisher", "float-sha", "float-branch",
              "action-scope", "action-sha", "action-comment", "bare-push", "push-comment")
    for block in blocks:
        mutant = without(script, block)
        for case in CASES:
            name, files, want_ok, _, tests = case[:5]
            if tests != block or name == "one bad among good":
                continue
            ok, out = run(mutant, files, opts(case).get("caller", CALLER))
            why = opts(case).get("mutant_text")
            good = ok != want_ok and (not why or why in out)
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
