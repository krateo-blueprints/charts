#!/usr/bin/env python3
"""Self-test for the reusable chart-defaults.yaml.

Runs the workflow's OWN check (the `python3 -I - ... <<'PY'` heredoc, extracted from the file) against
generated charts. Each case says the verdict (pass or fail) and text the output must contain. Then each
marked rule block is replaced by `pass` in turn and the cases written for it must flip. Exit 0 only if every
expectation holds.
"""
import json, os, re, shutil, subprocess, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "..", "..", ".github", "workflows", "chart-defaults.yaml")
CHART_YAML = "apiVersion: v2\nname: acme\nversion: CHART_VERSION\nappVersion: CHART_VERSION\n"


def extract():
    text = open(WF).read()
    m = re.search(r"-I - \"\$CHART_DIR\" \"\$ENFORCE\" <<'PY'\n(.*?)\n\s*PY\n", text, re.S)
    if not m:
        sys.exit("could not find the check heredoc in chart-defaults.yaml")
    return textwrap.dedent(m.group(1))


def prop(**kw):
    return {"type": "object", "properties": kw}


def leaf(default, typ=None):
    d = {"default": default}
    if typ:
        d["type"] = typ
    return d


def chart(root, rel, schema, values, with_schema=True):
    d = os.path.join(root, rel)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "Chart.yaml"), "w").write(CHART_YAML)
    if with_schema:
        open(os.path.join(d, "values.schema.json"), "w").write(json.dumps(schema, indent=2))
    if values is not None:
        open(os.path.join(d, "values.yaml"), "w").write(values)


def one(schema, values):
    return lambda root: chart(root, "chart", schema, values)


REFS = {"definitions": {"q": prop(enabled=leaf(False, "boolean"))}}

# name: (builder, expected exit-is-zero, substrings the output must contain)
CASES = {
    "aligned, nested, extra values key": (
        one(prop(a=leaf(1, "integer"), b=prop(c=leaf("x", "string")), d=leaf(True, "boolean")),
            "a: 1\nb:\n  c: x\nd: true\nonlyInValues: 7\n"),
        True, ["3 compared", "3 OK"]),
    "aligned through a $ref": (
        one(dict(REFS, properties={"q": {"$ref": "#/definitions/q"}}), "q:\n  enabled: false\n"),
        True, ["1 compared", "1 OK"]),
    "aligned through a $defs $ref": (
        one({"$defs": {"q": prop(enabled=leaf(False))}, "properties": {"q": {"$ref": "#/$defs/q"}}},
            "q:\n  enabled: false\n"),
        True, ["1 OK"]),
    "1 equals 1.0, deep object and array": (
        one(prop(n=leaf(1), f=leaf(2.0), o=leaf({"k": [1, {"z": None}]}), l=leaf([1, 2])),
            "n: 1.0\nf: 2\no:\n  k:\n    - 1\n    - z: null\nl:\n  - 1\n  - 2\n"),
        True, ["4 OK"]),
    "equal CHART_VERSION placeholders": (
        one(prop(tag=leaf("CHART_VERSION")), "tag: CHART_VERSION\n"), True, ["1 OK"]),
    "a schema with no default compares nothing": (
        one(prop(a={"type": "string"}), "a: x\n"), True, ["0 compared"]),
    "a vendored subchart is not a chart of the tree": (
        lambda root: (chart(root, "chart", prop(a=leaf(1)), "a: 1\n"),
                      chart(root, "chart/charts/dep", prop(a=leaf(1)), "a: 2\n")),
        True, ["1 chart(s)"]),
    "a fixture chart is not a chart of the tree": (
        lambda root: (chart(root, "chart", prop(a=leaf(1)), "a: 1\n"),
                      chart(root, "test/x", prop(a=leaf(1)), "a: 2\n")),
        True, ["1 chart(s)"]),
    "two charts, both aligned": (
        lambda root: (chart(root, "chart", prop(a=leaf(1)), "a: 1\n"),
                      chart(root, "config-chart", prop(b=leaf("x")), "b: x\n")),
        True, ["2 chart(s)", "2 OK"]),

    "value mismatch": (
        one(prop(a=leaf(1)), "a: 2\n"), False, ["a: schema default 1 != values.yaml 2"]),
    "missing values key": (
        one(prop(a=leaf(1)), "b: 2\n"), False, ["a: schema default 1, values.yaml has no key"]),
    "missing values.yaml": (
        lambda root: chart(root, "chart", prop(a=leaf(1)), None), False, ["values.yaml has no key"]),
    "type mismatch, string in schema": (
        one(prop(a=leaf("true")), "a: true\n"), False, ['schema default "true" != values.yaml true']),
    "type mismatch, string in values": (
        one(prop(a=leaf(True)), "a: \"true\"\n"), False, ['schema default true != values.yaml "true"']),
    "bool is not an integer": (
        one(prop(a=leaf(True)), "a: 1\n"), False, ["schema default true != values.yaml 1"]),
    "$ref mismatch": (
        one(dict(REFS, properties={"q": {"$ref": "#/definitions/q"}}), "q:\n  enabled: true\n"),
        False, ["q.enabled: schema default false != values.yaml true"]),
    "nested object mismatch": (
        one(prop(a=prop(b=prop(c=leaf("x")))), "a:\n  b:\n    c: y\n"),
        False, ['a.b.c: schema default "x" != values.yaml "y"']),
    "object default differs in one key": (
        one(prop(o=leaf({"k": 1, "j": 2})), "o:\n  k: 1\n  j: 3\n"), False, ["o: schema default"]),
    "array default differs": (
        one(prop(l=leaf([1, 2])), "l:\n  - 1\n  - 3\n"), False, ["l: schema default [1, 2] != values.yaml [1, 3]"]),
    "null in values, [] in schema": (
        one(prop(l=leaf([])), "l: null\n"), False, ["l: schema default [] != values.yaml null"]),
    "parent missing in values": (
        one(prop(a=prop(b=leaf(1))), "z: 1\n"), False, ["a.b: schema default 1, values.yaml has no key"]),
    "$ref that does not resolve": (
        one({"properties": {"q": {"$ref": "#/definitions/nope"}}}, "q: x\n"), False, ["does not resolve"]),
    "openstack-nova-operator-kog 0.1.10 shape": (
        one(prop(restdefinitions=prop(quota=prop(enabled=leaf(False, "boolean")))),
            "restdefinitions:\n  quota:\n    enabled: true\n"),
        False, ["restdefinitions.quota.enabled: schema default false != values.yaml true"]),
    "every mismatch is listed, not the first": (
        one(prop(a=leaf(1), b=leaf(2), c=leaf(3)), "a: 9\nb: 2\n"),
        False, ["a: schema default 1 != values.yaml 9", "c: schema default 3, values.yaml has no key"]),
    "a chart with no values.schema.json": (
        lambda root: chart(root, "chart", None, "a: 1\n", with_schema=False), False, ["no values.schema.json"]),
    "one chart without a schema among good ones": (
        lambda root: (chart(root, "chart", prop(a=leaf(1)), "a: 1\n"),
                      chart(root, "config-chart", None, "a: 1\n", with_schema=False)),
        False, ["config-chart: no values.schema.json"]),
    "a directory with no chart at all": (lambda root: open(os.path.join(root, "README.md"), "w").write("x\n"),
                                         False, ["no chart"]),
    "an empty directory": (lambda root: None, False, ["no chart"]),
    "only fixture charts": (lambda root: chart(root, "test/x", prop(a=leaf(1)), "a: 1\n"), False, ["no chart"]),
    "a directory that does not exist": (lambda root: shutil.rmtree(root), False, ["not a directory"]),
    "unparseable values.yaml": (one(prop(a=leaf(1)), "a: b: c\n"), False, ["cannot read"]),

    "items default is listed, not compared": (
        one(prop(l={"type": "array", "items": {"type": "object", "properties": {"t": leaf("IP")}}}), "l: null\n"),
        True, ["not compared: l[items].t: schema default \"IP\"", "1 not compared", "0 compared"]),
    "oneOf and additionalProperties defaults are listed": (
        one(prop(a={"oneOf": [leaf(1), {"type": "string"}]}, m={"additionalProperties": leaf(5)}), "a: 2\nm: null\n"),
        True, ["a[oneOf/0]", "m[additionalProperties]", "2 not compared"]),
    "an items default does not hide a real mismatch": (
        one(prop(a=leaf(1), l={"items": leaf(2)}), "a: 3\nl: null\n"),
        False, ["a: schema default 1 != values.yaml 3", "1 not compared"]),
    "an external $ref is listed, not compared": (
        one({"properties": {"q": {"$ref": "https://example.com/s.json"}}}, "q: 1\n"),
        True, ["not compared: q: $ref"]),
}

# Warn-only (enforce false): findings are ::warning:: and the step passes; an empty input still fails.
# Keys are (name, "warn"); the value is built like the others.
NOVA = prop(restdefinitions=prop(quota=prop(enabled=leaf(False, "boolean"))))
NOVA_VALUES = "restdefinitions:\n  quota:\n    enabled: true\n"
WARN = {
    "warn: the nova shape passes with a warning": (
        one(NOVA, NOVA_VALUES), True,
        ["::warning file=", "values.schema.json,title=chart-defaults::", "enabled: schema default false != values.yaml true",
         "findings reported as warnings"]),
    "warn: a missing key passes with a warning": (
        one(prop(a=leaf(1)), "b: 2\n"), True, ["::warning file=", "a: schema default 1, values.yaml has no key"]),
    "warn: a chart with no schema passes with a warning": (
        lambda root: chart(root, "chart", None, "a: 1\n", with_schema=False), True,
        ["::warning file=", "no values.schema.json"]),
    "warn: an aligned chart is silent": (one(prop(a=leaf(1)), "a: 1\n"), True, ["1 OK"]),
    "warn: a directory with no chart still fails": (lambda root: None, False, ["::error title=chart-defaults::no chart"]),
    "warn: a directory that does not exist still fails": (lambda root: shutil.rmtree(root), False, ["not a directory"]),
    "warn: an unreadable values.yaml still fails": (one(prop(a=leaf(1)), "a: b: c\n"), False, ["::error file=", "cannot read"]),
}
ENFORCED_ANNOTATION = ("enforce: the nova shape is an ::error::", one(NOVA, NOVA_VALUES), False,
                       ["::error file=", "values.schema.json,title=chart-defaults::"])

# The same two as committed fixtures, so a reader can open what the gate is shown.
FIXTURES = os.path.join(HERE, "fixtures")
CASES["committed fixture: aligned"] = (lambda root: shutil.copytree(os.path.join(FIXTURES, "aligned"), root, dirs_exist_ok=True),
                                       True, ["2 OK"])
CASES["committed fixture: nova-operator-kog 0.1.10"] = (
    lambda root: shutil.copytree(os.path.join(FIXTURES, "nova-operator-kog-0.1.10"), root, dirs_exist_ok=True),
    False, ["restdefinitions.quota.enabled: schema default false != values.yaml true"])

# rule block -> cases that must flip to the opposite verdict once the block is replaced by `pass`.
MUTANTS = {
    "warn-only": ["warn: the nova shape", "warn: a missing key", "warn: a chart with no schema"],
    "strict-bool": ["bool is not an integer"],
    "ref": ["$ref mismatch", "aligned through a $ref"],
    "missing-key": ["missing values key", "parent missing in values", "missing values.yaml"],
}


def run(script, case_builder, mode="true"):
    root = tempfile.mkdtemp(prefix="chart-defaults-")
    try:
        case_builder(root)
        p = subprocess.run([sys.executable, "-I", script, root, mode], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return p.returncode, p.stdout + p.stderr
    finally:
        shutil.rmtree(root, ignore_errors=True)


def mutate(src, block):
    pat = re.compile(rf"^([ \t]*)# \[rule:{re.escape(block)}\]\n.*?^[ \t]*# \[/rule:{re.escape(block)}\]\n", re.S | re.M)
    out, n = pat.subn(lambda m: f"{m.group(1)}pass\n", src)
    if n != 1:
        sys.exit(f"rule block {block} found {n} times, expected 1")
    return out


def main():
    src = extract()
    tmp = tempfile.mkdtemp(prefix="chart-defaults-script-")
    script = os.path.join(tmp, "check.py")
    open(script, "w").write(src)
    bad = []
    CASES[ENFORCED_ANNOTATION[0]] = ENFORCED_ANNOTATION[1:]
    for name, (builder, passes, needles) in list(CASES.items()) + [(n, v) for n, v in WARN.items()]:
        rc, out = run(script, builder, "false" if name in WARN else "true")
        verdict = (rc == 0) == passes
        if passes and rc not in (0,):
            verdict = False
        if not passes and rc == 0:
            verdict = False
        miss = [n for n in needles if n not in out]
        if not verdict or miss:
            bad.append(f"{name}: exit {rc}, wanted {'0' if passes else 'non-zero'}, missing {miss}\n{out}")
    print(f"{len(CASES) + len(WARN)} cases, {len(bad)} wrong")
    allblocks = set(re.findall(r"# \[rule:([a-z-]+)\]", src))
    if allblocks != set(MUTANTS):
        bad.append(f"rule blocks in the workflow {sorted(allblocks)} differ from those tested {sorted(MUTANTS)}")
    for block, flips in MUTANTS.items():
        mscript = os.path.join(tmp, f"mut-{block}.py")
        open(mscript, "w").write(mutate(src, block))
        for fragment in flips:
            names = [n for n in list(CASES) + list(WARN) if fragment in n]
            if not names:
                bad.append(f"mutant {block}: no case named like {fragment!r}")
            for n in names:
                builder, passes, needles = WARN[n] if n in WARN else CASES[n]
                rc, out = run(mscript, builder, "false" if n in WARN else "true")
                # Flipped: the verdict changed, or the output no longer says what the case requires
                # (a pass that compares nothing is not the same pass).
                same = (rc == 0) == passes and all(x in out for x in needles)
                if same or rc not in (0, 1):
                    bad.append(f"mutant {block} did not flip case {n!r} (exit {rc})\n{out}")
        print(f"mutant {block}: flips {flips}")
    shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    print("all expectations hold")


main()
