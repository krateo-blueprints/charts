#!/usr/bin/env python3
"""Run publish-chart.yaml's content gate against archives packaged here, and prove rule 13 is what
refuses a pre-release.

The gate's shell is read out of publish-chart.yaml (the step whose name starts "Content gate"), so
this tests the bytes callers run. Each case packages one chart with `helm package --version V`
into dist/ and runs that shell with the caller's SRC and CHANNEL, as the publisher does.

Then the mutation. The block between "# BEGIN rule-13" and "# END rule-13" is deleted from the
shell, and every case that rule 13 refused is run again; each must now be ACCEPTED. A refused case
that is still refused without rule 13 is being refused by something else, so it proves nothing
about rule 13, and this script fails.

Fails, rather than passing, when the step or the markers cannot be found or no case runs.
"""
import os
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "publish-chart.yaml")
SRC = "krateo-blueprints/example-repo"
BEGIN, END = "# BEGIN rule-13", "# END rule-13"
RULE13 = "pre-releases are never indexed"

# (channel, version, blueprint?, accepted?)
CASES = [
    ("blueprints", "0.1.0", True, True),
    ("blueprints", "10.20.300", True, True),
    ("operators", "1.2.3", False, True),
    ("blueprints", "0.3.74-main.gabc1234", True, False),
    ("blueprints", "0.3.74-dev.g0123abc", True, False),
    ("blueprints", "1.0.0-rc.1", True, False),
    ("blueprints", "1.0.0+build.7", True, False),
    ("operators", "1.2.3-alpha.1", False, False),
]
# Shapes semver itself rejects, so helm cannot package them and no caller can hand them over; the
# regex refuses them anyway, which is checked directly against the same pattern below.
UNPACKAGEABLE = ["v1.0.0", "01.0.0", "1.00.0"]


def gate_shell():
    doc = yaml.safe_load(open(WORKFLOW))
    steps = doc["jobs"]["publish"]["steps"]
    found = [s["run"] for s in steps if str(s.get("name", "")).startswith("Content gate")]
    if len(found) != 1:
        sys.exit(f"FAIL: expected one 'Content gate' step in {WORKFLOW}, found {len(found)}")
    return found[0]


def without_rule13(shell):
    lines = shell.splitlines(keepends=True)
    b = [i for i, line in enumerate(lines) if BEGIN in line]
    e = [i for i, line in enumerate(lines) if END in line]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        sys.exit(f"FAIL: the '{BEGIN}' / '{END}' markers are missing or out of order; the mutation "
                 "cannot be made, so nothing would prove rule 13 is tested")
    return "".join(lines[:b[0]] + lines[e[0] + 1:])


def package(tmp, version, blueprint):
    name = "demo-bp" if blueprint else "demo-op"
    chart = os.path.join(tmp, "src", name)
    os.makedirs(os.path.join(chart, "templates"))
    with open(os.path.join(chart, "Chart.yaml"), "w") as f:
        f.write(f"apiVersion: v2\nname: {name}\nversion: 0.0.0\n"
                "icon: https://example.com/icon.png\n"
                "keywords:\n  - example\n"
                f"sources:\n  - https://github.com/{SRC}\n")
    if blueprint:
        with open(os.path.join(chart, "values.schema.json"), "w") as f:
            f.write('{"type": "object"}\n')
        with open(os.path.join(chart, "compositiondefinition.yaml"), "w") as f:
            f.write("apiVersion: core.krateo.io/v1alpha1\nkind: CompositionDefinition\n"
                    f"metadata:\n  name: {name}\nspec:\n  chart:\n"
                    f"    url: oci://ghcr.io/krateo-blueprints/charts/{name}\n"
                    f"    version: {version}\n")
    dist = os.path.join(tmp, "dist")
    os.makedirs(dist, exist_ok=True)
    subprocess.run(["helm", "package", chart, "--version", version, "--destination", dist],
                   check=True, capture_output=True, text=True)


def run(shell, channel, version, blueprint):
    with tempfile.TemporaryDirectory() as tmp:
        package(tmp, version, blueprint)
        env = dict(os.environ, SRC=SRC, CHANNEL=channel)
        r = subprocess.run(["bash", "-c", shell], cwd=tmp, env=env, capture_output=True, text=True)
        return r.returncode == 0, r.stdout + r.stderr


def main():
    shell = gate_shell()
    mutant = without_rule13(shell)
    problems, ran = [], 0
    for channel, version, blueprint, want in CASES:
        ok, out = run(shell, channel, version, blueprint)
        ran += 1
        if ok != want:
            problems.append(f"{channel} {version}: {'accepted' if ok else 'refused'}, expected "
                            f"{'accepted' if want else 'refused'}\n{out}")
        elif not want and RULE13 not in out:
            problems.append(f"{channel} {version}: refused, but not by rule 13\n{out}")
        print(f"  {channel:10} {version:24} {'accepted' if ok else 'refused'}")
    for channel, version, blueprint, want in CASES:
        if want:
            continue
        ok, out = run(mutant, channel, version, blueprint)
        ran += 1
        if not ok:
            problems.append(f"MUTANT (rule 13 deleted) still refuses {channel} {version}: that case "
                            f"does not test rule 13\n{out}")
        print(f"  without rule 13: {channel:10} {version:24} {'accepted' if ok else 'refused'}")
    # The shapes helm cannot package: run the gate's own test expression on them.
    expr = [line.strip() for line in shell.splitlines() if "=~" in line and "$version" in line]
    # The test names the pattern by variable (PLAIN_VERSION, shared byte for byte with release-preflight.yaml), so
    # its definition is run with it: without it the variable is empty and an empty regex matches everything.
    defs = [line.strip() for line in shell.splitlines() if line.strip().startswith("PLAIN_VERSION=")]
    if len(expr) != 1 or len(defs) != 1:
        problems.append(f"expected one `$version =~` test and one PLAIN_VERSION definition in the gate, found {len(expr)} and {len(defs)}")
    else:
        # The gate's line is `if ! [[ ... ]]; then`; keep the bracket test, so exit 0 means "matches".
        test = expr[0].removeprefix("if ").split("; then")[0].strip().removeprefix("! ")
        for v in UNPACKAGEABLE:
            r = subprocess.run(["bash", "-c", f'{defs[0]}; version="$1"; {test}', "_", v])
            ran += 1
            if r.returncode == 0:
                problems.append(f"the gate's version test accepts {v!r}")
            print(f"  version test: {v:24} {'accepted' if r.returncode == 0 else 'refused'}")
    if ran == 0:
        sys.exit("FAIL: no case ran")
    if problems:
        print("\n".join(f"FAIL: {p}" for p in problems))
        sys.exit(1)
    print(f"OK: {ran} checks; rule 13 refuses every pre-release and only rule 13 does")


if __name__ == "__main__":
    main()
