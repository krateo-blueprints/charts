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
A renamed repository keeps GitHub's redirect from the old name.

**R2. The chart is at `chart/`. A per-account configuration chart, when there is one, is at
`config-chart/`. There is no other chart.** Not charts of the repository, and never published: anything
under a `test/`, `tests/`, `testdata/`, `fixtures/`, `e2e/`, `examples/`, `example/`, `samples/` or
`sample/` directory (a probe chart that must never ship lives there), and a vendored subchart, which is a
`charts/<x>/` inside a chart. A top-level `charts/<name>/` is a chart in the wrong place. A repository that
needs several independent charts is a blueprint, not a provider; how a chart is versioned is a separate
question (R4).

**R3. `chart/` is named after the repository, `config-chart/` after it plus `-config`.** The published
name then says where the source is: `oci://ghcr.io/krateo-blueprints/charts/github-provider-kog` is
`github-provider-kog/chart/`. Both charts' `home` and `sources` name the repository
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

**R5. A release is the shared one. *Advisory until krateo-platformops/.github's `release-oci.yaml`
gains a default-safe `dry_run`, runs the preflight strictly before any push, and documents a top-level
release-notes caller*; the check reports it as a warning until then, and a repository keeps its own
release until that version exists.** On a `X.Y.Z` tag the repository calls PUBLISHING.md's
`release-preflight.yaml` (rule 12), krateo-platformops/.github's `release-oci.yaml`, and `publish-chart.yaml`
(rule 1), in that order. There is no repository-specific `release-tag.yaml`: a fix to the shared release
reaches every repository at once, and only if no repository has its own.

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

## What is never done

- Publishing the same chart under its old and its new name as a way to avoid planning the rename.
- Exempting a repository from a rule in its own workflow. A rule that does not fit is changed here, for
  every repository.
