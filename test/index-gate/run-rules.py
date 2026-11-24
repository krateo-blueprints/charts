#!/usr/bin/env python3
"""The index gate's rules other than the version's, each proven by disabling it.

test/publish-chart/run-content-gate.py proves rule 13 (versions). This covers the rest of gate.sh that can run: the
archive's name, sources (rule 3), the channel (rule 2), the CompositionDefinition, the icon and the keywords.
One refusal of gate.sh has no case because it can't be reached: "no compositiondefinition.yaml in the archive". A
chart without one is an operator chart by the gate's own definition, so the channel rule has already refused it.

A case is a complete, valid chart with ONE thing wrong. It must be refused, with that rule's own message and no
other ::error::. Then the rule is disabled in a copy of gate.sh and the same archive is run again: it must now be
accepted. A case still refused without its rule is refused by something else and proves nothing. A mutation that
does not apply (its text is not there exactly once) is VOID, never a pass.

Needs bash, GNU tar (gtar where the system tar is not GNU), mikefarah yq and helm.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(ROOT, ".github", "actions", "index-gate", "gate.sh")
SRC = "krateo-blueprints/example-repo"
URL = "https://github.com/krateo-blueprints/example-repo"
OLD_URL = "https://github.com/krateo-blueprints/krateo-example-repo"


def void(msg):
    print("VOID: " + msg)
    sys.exit(2)


def chart(**over):
    """The fields of one chart; `over` changes them."""
    c = dict(name="demo", version="1.2.3", sources=[URL], icon="https://example.com/i.png", keywords=["k"],
             kind=None, schema=True, cd=True, cd_url="oci://ghcr.io/krateo-blueprints/charts/demo",
             cd_version="1.2.3", rename=None)
    c.update(over)
    return c


def package(tmp, c):
    d = os.path.join(tmp, "src", c["name"])
    os.makedirs(os.path.join(d, "templates"))
    y = [f"apiVersion: v2\nname: {c['name']}\nversion: {c['version']}\n"]
    if c["icon"] is not None:
        y.append(f"icon: {c['icon']}\n")
    if c["keywords"]:
        y.append("keywords:\n" + "".join(f"  - {k}\n" for k in c["keywords"]))
    if c["sources"]:
        y.append("sources:\n" + "".join(f"  - {s}\n" for s in c["sources"]))
    if c["kind"]:
        y.append(f"annotations:\n  krateo.io/kind: {c['kind']}\n")
    open(os.path.join(d, "Chart.yaml"), "w").write("".join(y))
    if c["schema"]:
        open(os.path.join(d, "values.schema.json"), "w").write('{"type": "object"}\n')
    if c["cd"]:
        open(os.path.join(d, "compositiondefinition.yaml"), "w").write(
            "apiVersion: core.krateo.io/v1alpha1\nkind: CompositionDefinition\nmetadata:\n  name: demo\nspec:\n"
            f"  chart:\n    url: {c['cd_url']}\n    version: {c['cd_version']}\n")
    dist = os.path.join(tmp, "dist")
    os.makedirs(dist, exist_ok=True)
    subprocess.run(["helm", "package", d, "--destination", dist], check=True, capture_output=True, text=True)
    if c["rename"]:
        os.rename(os.path.join(dist, f"{c['name']}-{c['version']}.tgz"), os.path.join(dist, c["rename"]))


def run(gate_text, channel, *charts):
    with tempfile.TemporaryDirectory() as tmp:
        for c in charts:
            package(tmp, c)
        g = os.path.join(tmp, "gate.sh")
        open(g, "w").write(gate_text)
        env = dict(os.environ, SRC=SRC, CHANNEL=channel)
        if shutil.which("gtar"):
            b = os.path.join(tmp, "bin")
            os.makedirs(b)
            os.symlink(shutil.which("gtar"), os.path.join(b, "tar"))
            env["PATH"] = b + os.pathsep + env["PATH"]
        r = subprocess.run(["bash", g, "dist"], cwd=tmp, env=env, capture_output=True, text=True)
        errors = [l for l in r.stdout.splitlines() if l.startswith("::error::")]
        if r.returncode not in (0, 1) or (r.returncode == 1 and not errors):
            void(f"the gate did not finish: exit {r.returncode}\n{r.stdout}{r.stderr}")
        return r.returncode == 0, errors


ACCEPTED = [
    ("a complete blueprint", "blueprints", chart()),
    ("a page set", "pages", chart(kind="page-set")),
    ("an operator chart", "operators", chart(schema=False, cd=False, icon=None, keywords=[])),
    ("sources in another letter case", "blueprints", chart(sources=["https://github.com/Krateo-Blueprints/Example-Repo"])),
    ("sources with a trailing slash", "blueprints", chart(sources=[URL + "/"])),
    # release-oci hands the gate every chart of a release at once.
    ("two charts in one release", "blueprints", chart(), chart(name="other", cd_url="oci://ghcr.io/krateo-blueprints/charts/other")),
    ("sources listing the repository second", "blueprints", chart(sources=["https://example.com/upstream", URL])),
]

ICON = '    *) echo "::error::$name: icon must be an absolute https URL, got \'$icon\'"; fail=1 ;;'
RULE2 = 'if [ "$CHANNEL" != "$want_channel" ]; then'
# (what is wrong, channel, chart, part of the rule's message, (gate text, what disables the rule))
SOURCES = ('|| { echo "::error::$name: Chart.yaml sources: must list ${src_url}, the repository that builds it"; fail=1; }', "|| true")
CD_URL = ('[ "$cd_url" = "$want_url" ] ||', "true ||")
CD_VER = ('[ "$cd_ver" = "$version" ] ||', "true ||")
REFUSED = [
    ("sources names the repository's OLD name (renamed)", "blueprints", chart(sources=[OLD_URL]), "sources: must list", SOURCES),
    ("sources is missing", "blueprints", chart(sources=[]), "sources: must list", SOURCES),
    ("sources names a repository this one's name begins", "blueprints", chart(sources=[URL + "-two"]), "sources: must list", SOURCES),
    ("sources names another owner's repository", "operators", chart(schema=False, cd=False, sources=["https://github.com/someone/example-repo"]), "sources: must list", SOURCES),
    ("a blueprint sent to pages", "pages", chart(), "belongs in blueprints, not pages", (RULE2, "if false; then")),
    ("a page set sent to blueprints", "blueprints", chart(kind="page-set"), "belongs in pages, not blueprints", (RULE2, "if false; then")),
    ("a blueprint sent to operators", "operators", chart(), "belongs in blueprints, not operators", (RULE2, "if false; then")),
    ("no icon", "blueprints", chart(icon=None), "icon must be", (ICON, "    *) : ;;")),
    ("an http icon", "blueprints", chart(icon="http://example.com/i.png"), "icon must be", (ICON, "    *) : ;;")),
    ("no keywords", "blueprints", chart(keywords=[]), "needs keywords", ("-gt 0 ] || {", "-gt 0 ] || true || {")),
    ("the CompositionDefinition installs another chart", "blueprints", chart(cd_url="oci://ghcr.io/krateo-blueprints/charts/other"), "CompositionDefinition installs 'oci", CD_URL),
    ("the CompositionDefinition installs another version", "blueprints", chart(cd_version="1.2.2"), "CompositionDefinition installs version '1.2.2'", CD_VER),
    ("the archive is named for another version", "blueprints", chart(rename="demo-9.9.9.tgz"), "Chart.yaml says demo 1.2.3",
     ('if [ "$(basename "$tgz")" != "${name}-${version}.tgz" ]; then', "if false; then")),
    # A chart without a schema is an operator chart: what refuses it in blueprints is the channel rule.
    ("no values.schema.json in blueprints", "blueprints", chart(schema=False), "belongs in operators, not blueprints", (RULE2, "if false; then")),
]


def main():
    if not os.path.isfile(GATE):
        void(f"{GATE} is missing")
    gate = open(GATE).read()
    bad, ran = [], 0
    for what, channel, *charts in ACCEPTED:
        ok, errors = run(gate, channel, *charts)
        ran += 1
        print(f"  {'ok  ' if ok else 'FAIL'} accepted: {what}")
        if not ok:
            bad.append(f"{what}: refused: {errors}")
    for what, channel, c, message, (old, new) in REFUSED:
        ok, errors = run(gate, channel, c)
        ran += 1
        if ok:
            bad.append(f"{what}: accepted")
        elif len(errors) != 1 or message not in errors[0]:
            bad.append(f"{what}: expected one error containing {message!r}, got {errors}")
        if gate.count(old) != 1:
            void(f"{what}: the text that disables its rule is in gate.sh {gate.count(old)} times, not once: {old}")
        mok, merrors = run(gate.replace(old, new), channel, c)
        ran += 1
        if not mok:
            bad.append(f"{what}: still refused with its rule disabled, so this case does not test it: {merrors}")
        print(f"  {'ok  ' if (not ok and mok) else 'FAIL'} refused by its own rule: {what}")
    # One bad chart refuses the release whichever comes first, and the good one is not blamed.
    for names in (("aaa", "demo"), ("zzz", "demo")):
        good = chart(name=names[0], cd_url=f"oci://ghcr.io/krateo-blueprints/charts/{names[0]}")
        ok, errors = run(gate, "blueprints", good, chart(sources=[OLD_URL]))
        ran += 1
        right = not ok and len(errors) == 1 and errors[0].startswith("::error::demo:")
        print(f"  {'ok  ' if right else 'FAIL'} a bad chart beside a good one ({names[0]}) is refused, by name")
        if not right:
            bad.append(f"a bad chart beside {names[0]}: {'accepted' if ok else errors}")
    if bad:
        print("\n".join("FAIL: " + b for b in bad))
        sys.exit(1)
    print(f"OK: {ran} runs; {len(ACCEPTED)} accepted, {len(REFUSED)} refused, each by its own rule and by nothing else")


if __name__ == "__main__":
    main()
