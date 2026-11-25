#!/usr/bin/env bash
# The krateo-blueprints index's content gate (PUBLISHING.md rules 1, 2, 3 and 13): does each packaged chart
# belong in the channel it is published to, and is its archive complete? ONE definition, used by publish-chart
# (at index time) and by krateo-platformops/.github release-oci (before anything is pushed), so a chart that
# would be refused by the index is refused before it reaches the registry, by the same rules.
#
# Usage: gate.sh <dir of .tgz>     Env: CHANNEL (blueprints | pages | operators), SRC (<owner>/<repo> that builds
#                                       the charts). Needs bash, GNU tar (--wildcards), yq (mikefarah), grep.
# Exit 0 when every archive passes, 1 otherwise, naming each failure as a ::error:: line. It names every archive
# it checks and ends with how many, and a directory with no archive is a failure: a gate that checked nothing
# must not read as one that passed.
#
# The body below is publish-chart.yaml's former "Content gate" step, unchanged but for the directory parameter;
# test/index-gate/run-identity.py proves that while publish-chart still carries the step inline.
set -euo pipefail
DIST="${1:?usage: gate.sh <dir of .tgz>}"
: "${CHANNEL:?CHANNEL is required (blueprints | pages | operators)}"
: "${SRC:?SRC is required (<owner>/<repo>)}"
# GNU tar (the runner's) matches a member pattern literally unless told --wildcards, so a
# bare '*/Chart.yaml' is "Not found in archive" and, under pipefail, fails the step for
# every chart. --no-wildcards-match-slash keeps '*' inside one path segment: the chart's
# own Chart.yaml, not those of its vendored charts/<dep>/ as well.
fail=0
shopt -s nullglob
archives=("${DIST}"/*.tgz)
shopt -u nullglob
if [ "${#archives[@]}" -eq 0 ]; then
  echo "::error::no .tgz in ${DIST}: the index gate has nothing to check"
  exit 1
fi
for tgz in "${archives[@]}"; do
  # Read each archive ONCE, then match with a here-string. Never `tar ... | grep -q`: grep -q
  # exits on its FIRST match, tar is then killed by SIGPIPE (141), and under `set -o pipefail`
  # the pipeline status BECOMES 141 -- so the file being present made the test FAIL. Whether
  # tar was still writing when grep exited depended on how much listing remained, so it only
  # bit the LARGEST charts: gcp-monitoring-dashboard, gcp-dlp-deidentifytemplate,
  # gcp-compute-urlmap and five more were rejected for "no values.schema.json" while carrying
  # it, in a run where 196 smaller charts passed. The same SIGPIPE truncated the `| yq` reads,
  # which is why one chart's name printed empty.
  members="$(tar tzf "$tgz")"
  chart_yaml="$(tar -xzO --wildcards --no-wildcards-match-slash -f "$tgz" '*/Chart.yaml')"
  name="$(yq -r '.name' <<< "$chart_yaml")"
  version="$(yq -r '.version' <<< "$chart_yaml")"
  echo "checking ${name} ${version} for ${CHANNEL}"
  if [ "$(basename "$tgz")" != "${name}-${version}.tgz" ]; then
    echo "::error::$(basename "$tgz"): Chart.yaml says ${name} ${version}"; fail=1; continue
  fi
  # Rule 13: pre-releases are never indexed. An index entry is never removed (see "What is
  # never done"), and the Marketplace offers the live index's versions newest first, so a
  # pre-release that got in would be on offer forever. Every channel, not only blueprints:
  # the index is the installable catalogue in all three. Plain X.Y.Z, no `v`, no leading
  # zeros, no -prerelease, no +build. Measured 2026-11-18: all 3,186 entries in the
  # blueprints and operators indexes already have this shape.
  # BEGIN rule-13 version check (test/publish-chart/run-content-gate.py removes this block
  # to prove its own cases can see it)
  # The pattern is defined once more, byte for byte, in release-preflight.yaml, which checks the release
  # version before anything is pushed; test/release-preflight/run-cases.py fails if the two differ.
  PLAIN_VERSION='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
  if ! [[ "$version" =~ $PLAIN_VERSION ]]; then
    echo "::error::$name ${version}: not a plain X.Y.Z release version; pre-releases are never indexed (PUBLISHING.md rule 13)"
    fail=1; continue
  fi
  # END rule-13 version check
  # Rule 3: every chart names its source repository, so a pinned chart can be traced to the
  # commit and CI run that built it.
  # GitHub owner and repository names are case-insensitive, and a builder writes them as the
  # author typed them, so compare lower-cased (frontend, 2026-11-07).
  src_url="https://github.com/${SRC}"
  src_lc="$(tr '[:upper:]' '[:lower:]' <<< "$src_url")"
  yq -r '.sources // [] | .[]' <<< "$chart_yaml" | tr '[:upper:]' '[:lower:]' | sed 's#/*$##' | grep -qxF "$src_lc" \
    || { echo "::error::$name: Chart.yaml sources: must list ${src_url}, the repository that builds it"; fail=1; }
  has_schema=no; has_cd=no
  grep -qxF "${name}/values.schema.json" <<< "$members" && has_schema=yes
  grep -qxF "${name}/compositiondefinition.yaml" <<< "$members" && has_cd=yes
  kind="$(yq -r '.annotations."krateo.io/kind" // ""' <<< "$chart_yaml")"
  if [ "$has_schema" = yes ] && [ "$has_cd" = yes ]; then
    if [ "$kind" = page-set ]; then want_channel=pages; else want_channel=blueprints; fi
  else
    want_channel=operators
  fi
  if [ "$CHANNEL" != "$want_channel" ]; then
    echo "::error::$name belongs in ${want_channel}, not ${CHANNEL} (PUBLISHING.md rule 2)"
    fail=1; continue
  fi
  [ "$CHANNEL" = operators ] && continue
  if [ "$has_cd" = yes ]; then
    cd_yaml="$(tar -xzO -f "$tgz" "${name}/compositiondefinition.yaml")"
    cd_url="$(yq -r 'select(.kind == "CompositionDefinition") | .spec.chart.url' <<< "$cd_yaml" | head -n1)"
    cd_ver="$(yq -r 'select(.kind == "CompositionDefinition") | .spec.chart.version' <<< "$cd_yaml" | head -n1)"
    want_url="oci://ghcr.io/krateo-blueprints/charts/${name}"
    [ "$cd_url" = "$want_url" ] || { echo "::error::$name: CompositionDefinition installs '${cd_url}', not ${want_url}"; fail=1; }
    [ "$cd_ver" = "$version" ] || { echo "::error::$name ${version}: its CompositionDefinition installs version '${cd_ver}'"; fail=1; }
  else
    echo "::error::$name: no ${name}/compositiondefinition.yaml in the archive; copy the stamped one into the chart before helm package"
    fail=1
  fi
  icon="$(yq -r '.icon // ""' <<< "$chart_yaml")"
  case "$icon" in
    https://*) : ;;
    *) echo "::error::$name: icon must be an absolute https URL, got '$icon'"; fail=1 ;;
  esac
  [ "$(yq -r '(.keywords // []) | length' <<< "$chart_yaml")" -gt 0 ] || { echo "::error::$name: Chart.yaml needs keywords, the Marketplace's tags"; fail=1; }
done
echo "index gate (${CHANNEL}): ${#archives[@]} archive(s) checked, $([ "$fail" = 0 ] && echo "every one passes" || echo "refused above")"
[ "$fail" = "0" ] || exit 1
