#!/usr/bin/env python3
"""publish-chart's two availability checks can fail, each for its own reason.

They are the only proof that what was published can be fetched with no credentials: "Every stored tarball downloads
without credentials" and "The Marketplace can install every chart published" (PUBLISHING.md rule 8). On a healthy
day both are green, which says nothing about whether they work. Here the steps' own shell, read out of
publish-chart.yaml, runs against a stand-in curl, helm and sleep that fail in one way at a time.

Every failing case is then run against a mutant, the step with the line that catches it removed, and must PASS there:
a case still failing would be failing for another reason. A mutation that does not apply is VOID.

Needs bash, GNU tar, mikefarah yq and helm (to package).
"""
import os
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "publish-chart.yaml")
STORED = "Every stored tarball downloads without credentials"
SERVED = "The Marketplace can install every chart published"
CHARTS = [("alpha", "1.2.3"), ("beta", "4.5.6")]


def void(msg):
    print("VOID: " + msg)
    sys.exit(2)


def step(name):
    found = [s["run"] for s in yaml.safe_load(open(WORKFLOW))["jobs"]["publish"]["steps"] if s.get("name") == name]
    if len(found) != 1:
        void(f"publish-chart.yaml has {len(found)} steps named {name!r}, not one")
    return found[0]


# The stand-ins fail when a credential reaches them, so a pass also proves the check ran without one.
CURL = r'''#!/usr/bin/env bash
out=""; url=""; ct=""; mt=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; --connect-timeout) ct="$2"; shift 2;; --max-time) mt="$2"; shift 2;; -H*|-u*|--user*|--header*|-n|--netrc*) echo "credential option $1" >&2; exit 9;; -*) shift;; *) url="$1"; shift;; esac; done
echo "curl $url connect-timeout=$ct max-time=$mt" >> "$LOG"
# A connection that stalls: real curl gives up at --max-time (exit 28); without one it never returns.
if [ -n "${HANG:-}" ]; then [ -n "$mt" ] && exit 28; exec tail -f /dev/null; fi
case "$url" in
  */index.yaml*) [ -z "${INDEX_DOWN:-}" ] || exit 22; cp "$INDEX" "$out" ;;
  *) case "$url" in *"${TARBALL_DOWN:-/none/}"*) exit 22 ;; esac; : > "$out" ;;
esac
'''
HELM = r'''#!/usr/bin/env bash
echo "helm $*" >> "$LOG"
[ -z "${GH_TOKEN:-}" ] || { echo "a credential reached helm" >&2; exit 9; }
[ "$2" != "${PULL_DOWN:-/none/}" ] || { echo "cannot pull $2" >&2; exit 1; }
'''


def run(shell, env, served, timeout=300):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "dist"))
        for n, v in CHARTS:
            d = os.path.join(tmp, "src", n)
            os.makedirs(d)
            open(os.path.join(d, "Chart.yaml"), "w").write(f"apiVersion: v2\nname: {n}\nversion: {v}\n")
            subprocess.run(["helm", "package", d, "--destination", os.path.join(tmp, "dist")], check=True, capture_output=True)
        index = os.path.join(tmp, "index.yaml")
        entries = "".join(f"  {n}:\n    - name: {n}\n      version: {v}\n" for n, v in served) or "  {}\n"
        open(index, "w").write("apiVersion: v1\nentries:\n" + entries)
        b = os.path.join(tmp, "bin")
        os.makedirs(b)
        for n, body in (("curl", CURL), ("helm", HELM), ("sleep", "#!/bin/sh\nexit 0\n")):
            open(os.path.join(b, n), "w").write(body)
            os.chmod(os.path.join(b, n), os.stat(os.path.join(b, n)).st_mode | stat.S_IXUSR)
        log = os.path.join(tmp, "log")
        open(log, "w").close()
        e = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"], LOG=log, INDEX=index, CHANNEL="operators",
                 GH_TOKEN="stand-in", RELEASES_BASE="https://store.invalid", REPO_URL="https://index.invalid/operators", **env)
        r = subprocess.run(["bash", "-c", shell], cwd=tmp, env=e, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr, open(log).read()


# (what fails, step, environment, entries served, what the step must say, mutation of the step)
CASES = [
    ("one stored tarball cannot be downloaded", STORED, {"TARBALL_DOWN": "beta-4.5.6"}, CHARTS, "beta-4.5.6.tgz is not anonymously downloadable",
     ('[ -n "$ok" ] ||', "true ||")),
    ("the served index lacks one version", SERVED, {}, [("alpha", "1.2.3"), ("beta", "4.5.5")], "still lacks: beta=4.5.6",
     ('if [ "${#missing[@]}" -gt 0 ]; then', "if false; then")),
    ("the served index lacks a chart", SERVED, {}, [("alpha", "1.2.3")], "still lacks: beta=4.5.6",
     ('if [ "${#missing[@]}" -gt 0 ]; then', "if false; then")),
    ("the served index can never be read", SERVED, {"INDEX_DOWN": "1"}, CHARTS, "still lacks: alpha=1.2.3 beta=4.5.6",
     ('missing=("${want[@]}")', "missing=()")),
    ("an indexed chart cannot be pulled", SERVED, {"PULL_DOWN": "beta"}, CHARTS, "cannot pull beta",
     ('--destination pulled', '--destination pulled || true')),
]


def main():
    steps = {n: step(n) for n in (STORED, SERVED)}
    bad, ran = [], 0
    for n in (STORED, SERVED):
        rc, out, log = run(steps[n], {}, CHARTS)
        ran += 1
        # Both charts were really asked for: a step that looked at nothing must not read as a pass.
        seen = all(c in log for c in ("alpha", "beta"))
        print(f"  {'ok  ' if rc == 0 and seen else 'FAIL'} passes when everything is there: {n}")
        if rc != 0 or not seen:
            bad.append(f"{n}: exit {rc}, both charts asked for: {seen}\n{out}{log}")
    for what, n, env, served, says, (old, new) in CASES:
        rc, out, _ = run(steps[n], env, served)
        ran += 1
        if steps[n].count(old) != 1:
            void(f"{what}: the text its mutation removes is in the step {steps[n].count(old)} times, not once: {old}")
        mrc, mout, _ = run(steps[n].replace(old, new), env, served)
        ran += 1
        ok = rc != 0 and says in out and mrc == 0
        print(f"  {'ok  ' if ok else 'FAIL'} fails: {what}")
        if rc == 0:
            bad.append(f"{what}: the step passed\n{out}")
        elif says not in out:
            bad.append(f"{what}: failed without saying {says!r}\n{out}")
        if mrc != 0:
            bad.append(f"{what}: still fails without the line that catches it\n{mout}")
    # A stalled connection must end inside the attempt: every curl carries both timeouts, and a hanging server
    # makes the step report what is missing instead of running until the job times out.
    for n, says in ((STORED, "is not anonymously downloadable"), (SERVED, "still lacks: alpha=1.2.3 beta=4.5.6")):
        rc, out, log = run(steps[n], {"HANG": "1"}, CHARTS, timeout=60)
        ran += 1
        calls = [l for l in log.splitlines() if l.startswith("curl ")]
        ok = rc == 1 and says in out and calls and all("connect-timeout=10 " in l and "max-time=30" in l for l in calls)
        print(f"  {'ok  ' if ok else 'FAIL'} a stalled connection ends within the timeout: {n}")
        if not ok:
            bad.append(f"{n}: stalled connection: exit {rc}, curls {calls}\n{out}")
        # Without --max-time the stand-in never answers; the run is cut off by the harness instead of finishing.
        try:
            mrc, _, _ = run(steps[n].replace("--max-time 30", ""), {"HANG": "1"}, CHARTS, timeout=10)
            bad.append(f"{n}: without --max-time the stalled connection still ended (exit {mrc})")
        except subprocess.TimeoutExpired:
            pass
        ran += 1
    # The pull drops the job's token: without that, the stand-in helm sees it and refuses.
    old = "env -u GH_TOKEN helm pull"
    if steps[SERVED].count(old) != 1:
        void(f"the token is dropped {steps[SERVED].count(old)} times, not once")
    rc, out, _ = run(steps[SERVED].replace(old, "helm pull"), {}, CHARTS)
    ran += 1
    ok = rc != 0 and "a credential reached helm" in out
    print(f"  {'ok  ' if ok else 'FAIL'} the pull runs without the job's token")
    if not ok:
        bad.append(f"with the token kept, the pull was not refused: exit {rc}\n{out}")
    if bad:
        print("\n".join("FAIL: " + x for x in bad))
        sys.exit(1)
    print(f"OK: {ran} runs; each availability check fails for its own reason and passes otherwise")


if __name__ == "__main__":
    main()
