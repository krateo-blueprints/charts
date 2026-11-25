#!/usr/bin/env python3
"""Self-test for the reusable repository-standard.yaml.

Runs the workflow's OWN check (the `python3 -I - <<'PY'` heredoc, extracted from the file) against
generated repository trees:
  - a repository that conforms passes;
  - each case breaks exactly one rule and must fail with that rule's id, and only that one; a case for an
    advisory rule (REPOSITORY.md: R5, R8's reference check) must pass and warn with that rule's id;
  - a Chart.yaml under a test fixture or a vendored subchart (chart/charts/<x>/) is not a chart of the
    repository, so it must not trip R2; a top-level charts/<name>/ IS one, in the wrong place, and must;
  - then every marked rule block (`# [rule:Rn]` ... `# [/rule:Rn]`) is deleted in turn, and each case
    that block exists for must flip to passing. Every rule has at least one case.
Exit 0 only if every expectation holds.
"""
import os, re, shutil, subprocess, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "..", "..", ".github", "workflows", "repository-standard.yaml")
NAME = "acme-provider-kog"

USES = {
    "release": ["krateo-platformops/.github/.github/workflows/release-oci.yaml"],
    "lint": [
        "krateo-blueprints/charts/.github/workflows/pinned-uses.yaml",
        "krateo-platformops/.github/.github/workflows/lint-docs.yaml",
    ],
    "security": ["krateo-platformops/.github/.github/workflows/security.yml"],
    "notes": ["krateo-platformops/.github/.github/workflows/release-notes.yaml"],
}
SHA = "0" * 40
DOCS = ["index.md", "overview.md", "configuration.md", "usage.md", "api.md", "examples.md", "log.md",
        "release.md", "llms.txt"]


def extract_check():
    text = open(WF).read()
    m = re.search(r"python3 -I - <<'PY'\n(.*?)\n\s*PY\n", text, re.S)
    if not m:
        sys.exit("could not find the check heredoc in repository-standard.yaml")
    return textwrap.dedent(m.group(1))


def write(root, rel, content=""):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(content)


def chart(name, repo=None):
    repo = repo or REPO_OF.get(name, NAME)
    url = f"https://github.com/krateo-blueprints/{repo}"
    return (f"apiVersion: v2\nname: {name}\nversion: CHART_VERSION\nappVersion: CHART_VERSION\n"
            f"home: {url}\nsources:\n  - {url}\n")


# A chart's repository, for charts the cases name after a different repository.
REPO_OF = {"krateo-acme-provider-kog": "krateo-acme-provider-kog", "krateo-acme-provider-kog-config": "krateo-acme-provider-kog",
           "acme-kog": "acme-kog", "acme-kog-config": "acme-kog"}


def workflow(paths, with_=""):
    jobs = "".join(f"  j{i}:\n    uses: {p}@{SHA} # 1.0.0\n{with_}" for i, p in enumerate(paths))
    return f"on:\n  push:\njobs:\n{jobs}"


RELEASE_WITH = "    permissions:\n      contents: read\n      packages: write\n    with:\n      index_channel: none\n"


def conforming(root):
    write(root, "chart/Chart.yaml", chart(NAME))
    write(root, "config-chart/Chart.yaml", chart(NAME + "-config"))
    write(root, "LICENSE", "Apache-2.0\n")
    write(root, "README.md", "# acme\n")
    write(root, ".github/dependabot.yml", "version: 2\nupdates:\n  - package-ecosystem: github-actions\n    directory: /\n")
    for d in DOCS:
        write(root, f"docs/{d}", "x\n")
    write(root, "hack/preflight-refs.py", "print('ok')\n")
    write(root, ".github/workflows/preflight-refs.yaml", "on:\n  push:\njobs:\n  p:\n    runs-on: ubuntu-latest\n")
    write(root, ".github/workflows/release-oci.yaml", workflow(USES["release"], RELEASE_WITH))
    write(root, ".github/workflows/lint.yaml", workflow(USES["lint"]))
    write(root, ".github/workflows/security.yml", workflow(USES["security"]))
    write(root, ".github/workflows/release-notes.yaml", workflow(USES["notes"]))


def rm(root, rel):
    p = os.path.join(root, rel)
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def move(root, src, dst):
    os.makedirs(os.path.dirname(os.path.join(root, dst)), exist_ok=True)
    shutil.move(os.path.join(root, src), os.path.join(root, dst))


# (case name, rule it must fail, repository name, mutation of the conforming tree)
CASES = [
    ("R1 krateo- prefix", "R1", "krateo-acme-provider-kog", lambda r: (
        write(r, "chart/Chart.yaml", chart("krateo-acme-provider-kog")),
        write(r, "config-chart/Chart.yaml", chart("krateo-acme-provider-kog-config")))),
    ("R1 no -provider-kog/-operator-kog suffix", "R1", "acme-kog", lambda r: (
        write(r, "chart/Chart.yaml", chart("acme-kog")),
        write(r, "config-chart/Chart.yaml", chart("acme-kog-config")))),
    ("R2 chart under helm/<name>/ instead of chart/", "R2", NAME, lambda r: (
        rm(r, "config-chart"), move(r, "chart", f"helm/{NAME}"))),
    ("R2 a third chart directory", "R2", NAME, lambda r: write(r, "extra/Chart.yaml", chart("extra"))),
    # A top-level charts/<name>/ is not a vendored subchart (nothing above it is a chart).
    ("R2 a top-level charts/<name>/ directory", "R2", NAME, lambda r: write(r, f"charts/{NAME}-helper/Chart.yaml", chart(f"{NAME}-helper"))),
    ("R3 chart not named after the repository", "R3", NAME, lambda r: write(r, "chart/Chart.yaml", chart("acme"))),
    ("R3 config chart not <repo>-config", "R3", NAME, lambda r: write(r, "config-chart/Chart.yaml", chart("acme-config"))),
    ("R3 sources still name the repository's former name", "R3", NAME, lambda r: write(
        r, "chart/Chart.yaml", chart(NAME).replace(f"  - https://github.com/krateo-blueprints/{NAME}", "  - https://github.com/krateo-blueprints/krateo-acme-kog"))),
    ("R3 home names another repository", "R3", NAME, lambda r: write(
        r, "config-chart/Chart.yaml", chart(NAME + "-config").replace(f"home: https://github.com/krateo-blueprints/{NAME}", "home: https://github.com/krateo-blueprints/elsewhere"))),
    ("R3 a Composition chart named otherwise, without source-repo", "R3", NAME, lambda r: (
        write(r, "chart/Chart.yaml", chart("acme-network")), write(r, "chart/compositiondefinition.yaml", "kind: CompositionDefinition\n"))),
    ("R3 a Composition chart whose source-repo names another repository", "R3", NAME, lambda r: (
        write(r, "chart/Chart.yaml", chart("acme-network") + "annotations:\n  krateo.io/source-repo: https://github.com/krateo-blueprints/elsewhere\n"),
        write(r, "chart/compositiondefinition.yaml", "kind: CompositionDefinition\n"))),
    ("R3 source-repo outside annotations does not count", "R3", NAME, lambda r: (
        write(r, "chart/Chart.yaml", chart("acme-network") + f"keywords:\n  - krateo.io/source-repo: https://github.com/krateo-blueprints/{NAME}\n"),
        write(r, "chart/compositiondefinition.yaml", "kind: CompositionDefinition\n"))),
    ("R4 hand-written version", "R4", NAME, lambda r: write(
        r, "chart/Chart.yaml", chart(NAME).replace("version: CHART_VERSION\napp", "version: 0.1.0\napp"))),
    ("R4 hand-written appVersion on the config chart", "R4", NAME, lambda r: write(
        r, "config-chart/Chart.yaml", chart(NAME + "-config").replace("appVersion: CHART_VERSION", "appVersion: 0.1.0"))),
    ("R5 no shared release-oci", "R5", NAME, lambda r: write(
        r, ".github/workflows/release-oci.yaml", workflow(["krateo-platformops/.github/.github/workflows/security.yml"]))),
    ("R5 release-oci without index_channel", "R5", NAME, lambda r: write(
        r, ".github/workflows/release-oci.yaml", workflow(USES["release"]))),
    ("R5 release-oci caller without packages: write", "R5", NAME, lambda r: write(
        r, ".github/workflows/release-oci.yaml", workflow(USES["release"], "    with:\n      index_channel: none\n"))),
    ("R5 publish-chart called beside release-oci", "R5", NAME, lambda r: write(
        r, ".github/workflows/index.yaml", workflow(["krateo-blueprints/charts/.github/workflows/publish-chart.yaml"]))),
    ("R5 release-preflight called beside release-oci", "R5", NAME, lambda r: write(
        r, ".github/workflows/preflight.yaml", workflow(["krateo-blueprints/charts/.github/workflows/release-preflight.yaml"]))),
    ("R5 chart-push used beside release-oci", "R5", NAME, lambda r: write(
        r, ".github/workflows/push.yaml", "on:\n  push:\njobs:\n  p:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: krateo-platformops/.github/.github/actions/chart-push@{SHA} # 1.0.0\n")),
    ("R5 a repository-specific release-tag.yaml", "R5", NAME, lambda r: write(
        r, ".github/workflows/release-tag.yaml", "on:\n  push:\njobs:\n  r:\n    runs-on: ubuntu-latest\n")),
    ("R6 no LICENSE", "R6", NAME, lambda r: rm(r, "LICENSE")),
    ("R6 Dependabot without github-actions", "R6", NAME, lambda r: write(
        r, ".github/dependabot.yml", "version: 2\nupdates:\n  - package-ecosystem: pip\n")),
    ("R7 docs bundle missing one page", "R7", NAME, lambda r: rm(r, "docs/api.md")),
    ("R8 no pinned-uses", "R8", NAME, lambda r: write(
        r, ".github/workflows/lint.yaml", workflow([u for u in USES["lint"] if "pinned-uses" not in u]))),
    ("R8 no preflight-refs workflow", "R8", NAME, lambda r: rm(r, ".github/workflows/preflight-refs.yaml")),
]

# Advisory rules (REPOSITORY.md): the case must still PASS (exit 0) and print a warning for its rule.
ADVISORY = {"R5 no shared release-oci", "R5 release-oci without index_channel", "R5 release-oci caller without packages: write", "R5 publish-chart called beside release-oci",
            "R5 release-preflight called beside release-oci", "R5 chart-push used beside release-oci",
            "R5 a repository-specific release-tag.yaml",
            "R8 no preflight-refs workflow"}

# Must pass: Chart.yaml files that are not charts of the repository.
PASSES = [
    ("conforms", NAME, lambda r: None),
    ("conforms without a config chart", NAME, lambda r: rm(r, "config-chart")),
    ("a Composition chart named after what it provisions, with source-repo", NAME, lambda r: (
        write(r, "chart/Chart.yaml", chart("acme-network") + f"annotations:\n  krateo.io/source-repo: https://github.com/krateo-blueprints/{NAME}\n"),
        write(r, "chart/compositiondefinition.yaml", "kind: CompositionDefinition\n"))),
    ("a test fixture's Chart.yaml is not a chart", NAME, lambda r: write(r, "test/fixtures/x/Chart.yaml", chart("x"))),
    ("a vendored subchart is not a chart", NAME, lambda r: write(r, "chart/charts/dep/Chart.yaml", chart("dep"))),
    ("a vendored subchart of the config chart is not a chart", NAME, lambda r: write(r, "config-chart/charts/dep/Chart.yaml", chart("dep"))),
]


def run(check, name, mutate):
    root = tempfile.mkdtemp()
    try:
        conforming(root)
        mutate(root)
        p = subprocess.run([sys.executable, "-I", "-c", check], env={"ROOT": root, "REPO_NAME": name, "PATH": os.environ["PATH"]},
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    finally:
        shutil.rmtree(root)


def rules_in(out):
    return sorted(set(re.findall(r"^\s+(R\d+):(?!.*\(advisory\)$)", out, re.M)))


def warned_in(out):
    return sorted(set(re.findall(r"^\s+(R\d+):.*\(advisory\)$", out, re.M)))


def main():
    check = extract_check()
    bad = []
    for label, name, mutate in PASSES:
        rc, out = run(check, name, mutate)
        ok = rc == 0
        print(f"{'ok  ' if ok else 'FAIL'} passes: {label}")
        if not ok:
            bad.append(label); print(textwrap.indent(out, "      "))
    for label, rule, name, mutate in CASES:
        rc, out = run(check, name, mutate)
        if label in ADVISORY:
            got = warned_in(out)
            ok = rc == 0 and got == [rule] and rules_in(out) == []
            print(f"{'ok  ' if ok else 'FAIL'} warns:   {label} -> {got}")
        else:
            got = rules_in(out)
            ok = rc == 1 and got == [rule] and warned_in(out) == []
            print(f"{'ok  ' if ok else 'FAIL'} refuses: {label} -> {got}")
        if not ok:
            bad.append(label); print(textwrap.indent(out, "      "))
    # Each rule block, deleted, must let every case written for it pass.
    blocks = sorted(set(re.findall(r"# \[rule:(R\d+)\]", check)))
    for rule in blocks:
        cut = re.sub(rf"\n[ \t]*# \[rule:{rule}\].*?# \[/rule:{rule}\]", "", check, flags=re.S)
        if cut == check:
            bad.append(f"block {rule} not found"); continue
        mine = [c for c in CASES if c[1] == rule]
        if not mine:
            bad.append(f"rule {rule} has no case"); print(f"FAIL rule {rule} has no case"); continue
        for label, _, name, mutate in mine:
            rc, out = run(cut, name, mutate)
            # Without the block the case passes silently: no failure and, for an advisory rule, no warning.
            ok = rc == 0 and rule not in warned_in(out) and rule not in rules_in(out)
            print(f"{'ok  ' if ok else 'FAIL'} without block {rule}, '{label}' passes silently")
            if not ok:
                bad.append(f"without {rule}: {label}"); print(textwrap.indent(out, "      "))
    if bad:
        print(f"\n{len(bad)} expectation(s) failed")
        sys.exit(1)
    print(f"\nall {len(PASSES) + len(CASES)} cases and {len(blocks)} rule deletions hold")


if __name__ == "__main__":
    main()
