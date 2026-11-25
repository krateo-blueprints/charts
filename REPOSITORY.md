# How every krateo-blueprints repository is laid out

[PUBLISHING.md](PUBLISHING.md) decides how a chart is published. This file decides what a repository
looks like before that: its name, where its charts live, what they are called, how a release is cut and
which files and checks it carries. `repository-standard.yaml` checks it.

## Why there is a standard

The organisation grew one repository at a time, and each one solved layout, naming and release on its
own. Audited on 2026-11-22, the 18 provider and operator repositories used five chart layouts (`chart/`,
`helm/<name>/`, `charts/<name>/`, `compositions/<name>/`, none), three naming patterns, and two release
paths, nine of them a repository-specific workflow. The same question ("where is the source of this
chart, and how is it released?") had a different answer in each, and every repository-specific release
was one more place for a fix in the shared one to be missing.

One repository already did everything the others needed: **azuredevops-provider-kog** is the reference.
When this file and that repository disagree, this file wins and the repository is fixed.

## Scope

- **Provider and operator repositories**: every repository whose name ends in `-provider-kog` or
  `-operator-kog`, and every repository that should (rule R1). This file is their standard.
- **Blueprints** (`*-blueprint`): their standard is being written; until it is, they follow
  PUBLISHING.md only.
- Other repositories (sites, sandboxes, fixtures) are out of scope.

## The standard

**R1. The name is `<vendor>-provider-kog`.** A repository that wraps a Kubernetes operator rather than a
REST API is `<vendor>-operator-kog`. There is no `krateo-` prefix: the organisation already says Krateo.
The check refuses the prefix and any other suffix. It can't know what a repository wraps, so it accepts
both suffixes: **no build ever fails on `-operator-kog` over a REST API**, and choosing the right one is
the owner's to do. A repository of several independent charts is a blueprint (R2) and R1 does not name it.

**R1 and R3 land together.** R3 takes the chart's name, `home` and `sources` from the repository's name,
so renaming either alone fails. Where the chart is installed anywhere, the repository rename therefore
waits for the plan in [Changing a published name](#changing-a-published-name); it is not a step of
adopting the rest of this standard. GitHub redirects the old name for browsing, git and the API, but
**a redirect does not satisfy R3 or publish-chart**, which compare the name as a string.

**R2. The chart is at `chart/`. A per-account configuration chart, when there is one, is at
`config-chart/`. There is no other chart.** Not charts of the repository, and never published: anything
under a `test/`, `tests/`, `testdata/`, `fixtures/`, `e2e/`, `examples/`, `example/`, `samples/` or
`sample/` directory (a probe chart that must never ship lives there), and a vendored subchart, which is a
`charts/<x>/` inside a chart. A top-level `charts/<name>/` is a chart in the wrong place. **A chart that must never ship (a probe, a test fixture) lives only under one of
those directory names**: krateo-platformops/.github release-oci prunes exactly them from discovery
(and `chart_root` itself is never pruned, only what is below it). For the blueprints and pages index
channels the index gate refuses such a chart independently (no CompositionDefinition computes as
`operators`), but for **`operators`** a chart without one is exactly what qualifies, so there the
directory name is the only thing between a fixture and the registry and the index. A repository that
needs several independent charts is a blueprint, not a provider; how a chart is versioned is a separate
question (R4).

**A gate that discovers what it checks passes when it finds nothing**, unless it is written not to. On a
real move to `chart/`, two chart gates globbing the old path passed with `0 chart(s)` checked and the
build green: one returned 0 on an empty list, one shell loop kept its glob literal without `nullglob`
and skipped its one iteration. The careless move (a bare `git mv`) failed loudly elsewhere; the careful
one, with those failures fixed, left the gates disarmed. The same shape needs no move at all: an asset
check globbing `chart/assets/*.yaml` printed `0 assets` and exited 0 with every asset removed. So a
repository names the paths R2 fixes (`chart/`, and `config-chart/` when there is one) instead of
discovering them, makes an empty set an error in every gate that counts, and reads a gate's log for its
count, not its exit code. The shared release already refuses an empty set. Two more checks close it: the
gate must also **bite** (a commit that reintroduces a known defect fails it; a gate that speaks may only
have gone quiet somewhere new), and it must do both **in the run that gates the merge**. A repository
held a script that refused an empty set in as many words, and no workflow ran it.

**R3. `chart/` is named after the repository, `config-chart/` after it plus `-config`. A `chart/` that
ships a Composition instead (it carries `compositiondefinition.yaml`) is named after what the Composition
provisions, and its `krateo.io/source-repo` annotation names the repository.** The annotation names the
repository as it is now, like `home` and `sources`, and moves with them in the rename's pull request:
written ahead of an R1 rename it would name a repository that doesn't exist yet, and repository-standard
refuses it. The published name or the
annotation then says where the source is: `oci://ghcr.io/krateo-blueprints/charts/github-provider-kog` is
`github-provider-kog/chart/`. A Composition does not take the repository's name, which belongs to the
provider's own chart. What keeps a name to one owner is `sources`, not the name (below), and a pin never
names a source repository: installer pins chart names against a registry, and already installs one
repository's charts under three names. Both charts' `home` and `sources` name the repository
(`https://github.com/krateo-blueprints/<repo>`): publish-chart refuses a chart whose `sources` does not
list its publishing repository, and compares a string, so a GitHub redirect does not satisfy it. **A
repository rename (R1) therefore updates `home` and `sources` in the same change**, and is never a GitHub
setting alone.

**R4. Versions follow [PUBLISHING.md rule 4](PUBLISHING.md); for a provider that is the default shape.**
Rule 4 is the one definition of how a chart is versioned, and this file does not restate it. A provider
chart (no CompositionDefinition) versions with its repository, so `version` and `appVersion` are both the
`CHART_VERSION` placeholder, stamped from the release tag. A provider ships no image (oasgen-provider
spawns the controller), so there is no separate application version to report, and a hand-maintained one
drifts: one was found at `0.1.9` while the repository released `0.15.0`. **Every step that stamps the
placeholder substitutes it globally**: a substitution anchored to `version:` silently leaves `appVersion`
as the literal placeholder, and helm accepts that without a word. Charts whose version is a served API
version (rule 4's second shape) keep literal versions; they belong to blueprint repositories.

**R5. A release is the shared one. *Advisory until krateo-platformops/.github's `release-oci` 2.1.0*,
the first version every index channel can adopt. R5 becomes a failure in the charts release that follows
release-oci 2.1.0, announced to every repository's owner first; until then the check warns, and a
repository keeps its own release, so that it migrates once.** On a `X.Y.Z` tag the repository calls
krateo-platformops/.github's `release-oci.yaml` with an explicit `index_channel`, and nothing else for the
release: release-oci itself runs PUBLISHING.md's `release-preflight.yaml` (rule 12) before any push and,
for a channel, `publish-chart.yaml` (rule 1) after it. A repository that also calls `publish-chart.yaml`
or `release-preflight.yaml` beside release-oci runs them twice. There is no repository-specific
`release-tag.yaml`: a fix to the shared release reaches every repository at once, and only if no
repository has its own.

The release-oci version depends on the channel:

| `index_channel` | Charts | release-oci |
| --- | --- | --- |
| `none` | installed by the installer or by hand, never in an index | 2.0.0 or later |
| `blueprints`, `pages`, `operators` | listed in that Marketplace index | 2.1.0 or later |

2.0.0 indexes only the charts a run pushed, so re-running a release that pushed and then failed to index
cannot finish it. 2.1.0 indexes every chart of the release, pushed or already published. A channel
other than `none` passes `charts_publish_token` (the org secret `CHARTS_PUBLISH_TOKEN`), and `blueprints`
or `pages` also sets `oci_repo: oci://ghcr.io/krateo-blueprints/charts` explicitly.

**The calling job grants what release-oci needs**, because a called workflow can't have more than its
caller allows, and a repository's default is read-only:

```yaml
jobs:
  release:
    permissions:
      contents: read
      packages: write
    uses: krateo-platformops/.github/.github/workflows/release-oci.yaml@<full SHA> # X.Y.Z
```

Without it the run ends at startup with no job, no log and no error through the API: the reason
("requesting 'packages: write', but is only allowed 'packages: read'") is shown only on the run's web
page. Nothing is pushed.

**A first-time caller can't rehearse before merging.** A `workflow_dispatch` workflow must be on the
default branch before it can be dispatched. So the order is merge (the caller triggers only on tags and
dispatch, so a merge publishes nothing), then a dry-run dispatch **with an explicit version**, then the
tag. release-oci takes the version from the ref when `chart_version` is empty: on a tag the ref is the
version, on a dispatch it is a branch, and release-preflight refuses `main` before anything is pushed.
So a caller that offers dispatch passes both:

```yaml
    with:
      dry_run: ${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}
      chart_version: ${{ github.event_name == 'workflow_dispatch' && inputs.chart_version || '' }}
```

with `dry_run` defaulting to `true` and an optional `chart_version` input. On a tag both are false or
empty, and the tag decides; a mistyped dispatch rehearses; a dispatch without a version is refused with
the reason.

Migrating removes more than `release-tag.yaml`. A repository that adopted PUBLISHING.md rule 12 (its own
`release-preflight.yaml` call) and rule 14 (pushing through the `chart-push` action) did so on purpose,
and release-oci now does both. So migrating deletes, beside the call to release-oci: the
`release-tag.yaml`, the `release-preflight.yaml` job, the `chart-push` push path and any
`publish-chart.yaml` or index job. Kept, a conscientious caller publishes twice. Release assets and
release notes stay top-level callers. The release asset is named after the chart
(`compositiondefinition-<chart>.yaml`), so a repository whose asset was named after a folder changes
that file's name at its first release through release-oci, and a consumer that downloads it by name
must follow. A publish-index log that says `not served yet` on its first poll, on a run that ends
green, is the index's propagation: the step polls until the new version is served.

**R6. The repository carries `LICENSE`, `README.md` and `.github/dependabot.yml` for the
`github-actions` ecosystem.** Dependabot is what keeps the SHA pins of rule 9 current.

**R7. The docs bundle is complete**: `docs/index.md`, `overview.md`, `configuration.md`, `usage.md`,
`api.md`, `examples.md`, `log.md`, `release.md` and `llms.txt`.

**R8. The shared checks run**: `pinned-uses.yaml` (PUBLISHING.md rule 9), krateo-platformops/.github's
`lint-docs.yaml`, `security.yml` and `release-notes.yaml`, and a live reference check run by
`.github/workflows/preflight-refs.yaml`. *The reference check is advisory until it is a shared reusable
here*: one copy per repository would drift, so the check warns about it and does not fail.

## Checking a repository

```yaml
jobs:
  repository-standard:
    uses: krateo-blueprints/charts/.github/workflows/repository-standard.yaml@<full SHA> # X.Y.Z
```

It reads the caller's checkout only: no network, no token, no write. It prints every deviation with its
rule and exits 1 if there is one. `test-repository-standard.yaml` proves each rule fires: it deletes each
rule's block in turn and requires the case written for it to flip.

## Changing a published name

Moving a chart to `chart/` is a code change. **Renaming a published chart is not**: wherever the chart
is installed, its old name is a live release, and on a Krateo cluster a live CompositionDefinition whose
removal can take the generated CRDs and every custom resource with them. So a rename that this standard
requires is planned per cluster with the installer's owner: the new name added and the old one retired
in one installer change, the old values key kept until no live installation carries it, and the
installed custom resources proven to survive the move before any cluster is touched.

In a repository rename, every place that names the repository (`home`, `sources`, and the
`krateo.io/source-repo` annotation where the chart carries one) changes in one pull request, merged right
after the GitHub rename, with no release tagged in between. Versions already published keep the old
address and are not republished: see [PUBLISHING.md rule 6](PUBLISHING.md).

## What is never done

- Publishing the same chart under its old and its new name as a way to avoid planning the rename.
- Exempting a repository from a rule in its own workflow. A rule that does not fit is changed here, for
  every repository.
