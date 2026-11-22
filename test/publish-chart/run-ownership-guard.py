#!/usr/bin/env python3
"""Self-test for the publisher's ownership guard (publish-chart.yaml, "Ownership guard", rule 6).

Runs the guard's own shell, read out of publish-chart.yaml, against a fake channel index and archives
packaged here, with a stub `gh` on PATH that answers `gh api repos/<r> --jq .full_name` from a table
(a renamed repository answers at its old name with its new one, as GitHub does) and fails everything
else:
  - a name nobody owns yet, and a name the publisher owns, pass;
  - a name owned by the publisher's FORMER name (renamed on GitHub) passes;
  - a name owned under the organisation's former owner prefix (braghettos/) passes;
  - a name owned by another repository is refused;
  - a name whose recorded owner cannot be resolved (lookup fails) is refused unless it IS the publisher.
Then it replaces canon() with a lowercase-only version and requires the renamed case to be refused:
the case passes because of canon, not by accident. Last, canon() must be byte-identical in the
ownership guard and the blob-store guard, the two places that compare owners.

Needs GNU tar (--wildcards) and mikefarah yq, as on the runner.
"""
import os, re, subprocess, sys, tarfile, tempfile, textwrap, io

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "..", "..", ".github", "workflows", "publish-chart.yaml")
ME = "krateo-blueprints/acme-provider-kog"
# The stub's view of GitHub: name -> current full_name. Anything absent fails, like a 404.
GITHUB = {
    "krateo-blueprints/acme-provider-kog": "krateo-blueprints/acme-provider-kog",
    "krateo-blueprints/krateo-acme-kog": "krateo-blueprints/acme-provider-kog",   # renamed
    "krateo-blueprints/other-provider-kog": "krateo-blueprints/other-provider-kog",
}


def step(text, name):
    m = re.search(rf"- name: {re.escape(name)}\n(?:.*\n)*?\s+run: \|\n((?:[ \t]+.*\n|\n)+?)(?=\s+- name:|\Z)", text)
    if not m:
        sys.exit(f"step {name!r} not found in publish-chart.yaml")
    return textwrap.dedent(m.group(1))


def canon_block(script):
    m = re.search(r"# \[canon\].*?# \[/canon\]\n", script, re.S)
    return m.group(0) if m else None


STUB = r'''#!/usr/bin/env python3
import json, os, sys
table = json.load(open(os.environ["STUB_GITHUB"]))
a = sys.argv[1:]
if len(a) >= 2 and a[0] == "api" and a[1].startswith("repos/"):
    r = a[1][len("repos/"):].lower()
    if r in table:
        print(table[r]); sys.exit(0)
    print('{"message":"Not Found"}', file=sys.stderr); sys.exit(1)
sys.exit(1)
'''


def archive(path, name):
    data = f"apiVersion: v2\nname: {name}\nversion: 1.0.0\n".encode()
    with tarfile.open(path, "w:gz") as t:
        ti = tarfile.TarInfo(f"{name}/Chart.yaml"); ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))


def run(script, owner_annotation):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "gh-pages", "operators"))
    os.makedirs(os.path.join(d, "dist"))
    os.makedirs(os.path.join(d, "bin"))
    archive(os.path.join(d, "dist", "acme-1.0.0.tgz"), "acme")
    if owner_annotation is None:
        idx = "apiVersion: v1\nentries: {}\n"
    else:
        idx = ("apiVersion: v1\nentries:\n  acme:\n    - name: acme\n      version: 0.9.0\n"
               f"      annotations:\n        krateo.io/source-repo: {owner_annotation}\n")
    open(os.path.join(d, "gh-pages", "operators", "index.yaml"), "w").write(idx)
    stub = os.path.join(d, "bin", "gh")
    open(stub, "w").write(STUB); os.chmod(stub, 0o755)
    import json
    tbl = os.path.join(d, "github.json"); json.dump(GITHUB, open(tbl, "w"))
    env = {"PATH": os.path.join(d, "bin") + ":" + os.environ["PATH"], "CHANNEL": "operators", "SRC": ME,
           "STUB_GITHUB": tbl, "HOME": d}
    p = subprocess.run(["bash", "-c", script], cwd=d, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


CASES = [
    # (label, recorded owner or None for no entry, expected exit code 0 pass / nonzero refuse)
    ("a name nobody owns yet passes", None, 0),
    ("a name the publisher owns passes", ME, 0),
    ("a name owned by the publisher's former name passes", "krateo-blueprints/krateo-acme-kog", 0),
    ("the organisation's former prefix passes", "braghettos/acme-provider-kog", 0),
    ("another repository's name is refused", "krateo-blueprints/other-provider-kog", 1),
    ("an owner that cannot be resolved is refused", "krateo-blueprints/gone-kog", 1),
]


def main():
    text = open(WF).read()
    guard = step(text, "Ownership guard")
    store = step(text, "Store tarballs in this repository's Releases (shared blob store)")
    bad = []
    for label, owner, want in CASES:
        rc, out = run(guard, owner)
        ok = (rc == 0) == (want == 0)
        print(f"{'ok  ' if ok else 'FAIL'} {label} (exit {rc})")
        if not ok:
            bad.append(label); print(textwrap.indent(out, "      "))
    # canon is what makes the renamed case pass.
    lower_only = ('canon() { tr \'[:upper:]\' \'[:lower:]\' <<< "$1" | sed \'s#^braghettos/#krateo-blueprints/#\'; }\n')
    cut = guard.replace(canon_block(guard), lower_only)
    rc, out = run(cut, "krateo-blueprints/krateo-acme-kog")
    ok = rc != 0
    print(f"{'ok  ' if ok else 'FAIL'} without canon's lookup, the renamed owner is refused (exit {rc})")
    if not ok:
        bad.append("canon deletion")
    # One definition, two places.
    a, b = canon_block(guard), canon_block(store)
    ok = a is not None and a == b
    print(f"{'ok  ' if ok else 'FAIL'} canon() is byte-identical in the ownership and blob-store guards")
    if not ok:
        bad.append("canon identical")
    if bad:
        print(f"\n{len(bad)} expectation(s) failed"); sys.exit(1)
    print(f"\nall {len(CASES)} cases, the canon deletion and the identity check hold")


if __name__ == "__main__":
    main()
