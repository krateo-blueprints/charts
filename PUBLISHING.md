# How every krateo-blueprints chart is published

This is the one publishing standard for every chart in the krateo-blueprints organisation. Diego
decided it on 2026-11-07. A repository that publishes charts follows it. Anything it doesn't cover
is decided here first and then applied everywhere, never repository by repository.

The rules that can be checked are checked by `publish-chart.yaml`, so a caller that ignores them
fails its release instead of publishing something wrong.

## Why there is a standard

On 2026-11-07, the Marketplace was installing OpenStack 0.2.0 when GHCR held 0.3.36, and
`openstack-nova-operator-kog` 0.1.0, an architecture its team had deleted. About 25 repositories
pushed only to GHCR, and the Marketplace never saw them. The 11 that did call the publisher all
fell back to an org token that had stopped authenticating, and nothing has entered the index since
2026-10-09. The publisher also created one GitHub release per chart in each caller, and five
callers' "Latest" ended up on a single chart. Two published archives carried a CompositionDefinition
pinned to a version other than their own (gcp 0.1.5 shipping 0.1.0, azure 0.1.3 shipping 0.1.0).
No release reported any of this.

## The standard

1. **Every chart is packaged once and published twice, with the same bytes.**
   - **GHCR:** first, at `oci://ghcr.io/krateo-blueprints/charts/<name>:<version>`. Every chart in
     this organisation publishes to that registry and no other.
   - **The index here:** second, by `publish-chart.yaml`. A chart that is in GHCR and not in the
     index is not published, because the Marketplace installs from the index and nothing
     re-resolves it against GHCR.

   GHCR is the source of truth, so what goes to the index is the archive GHCR holds, not a second
   package. A repository that packages its own charts hands the archives it pushed. A repository
   on the shared `krateo-platformops/.github` `release-oci.yaml` pulls each chart back from GHCR
   after that workflow runs. That covers a version the workflow skipped because it was already
   published identically: a fresh `helm package` would have new mtimes and different bytes.

2. **The channel follows from the content, not from preference.**
   - **`blueprints`:** a chart with `values.schema.json` and a CompositionDefinition.
   - **`operators`:** every other chart, such as operators, KOGs without a CompositionDefinition,
     and helper or CRD charts.

   The publisher refuses a non-blueprint in `blueprints` and a blueprint in `operators`, so the
   same chart can never be in the wrong one.

3. **A blueprint archive is self-describing.** The archive must contain, at its root:
   - `values.schema.json`;
   - `compositiondefinition.yaml`, whose `spec.chart.url` is
     `oci://ghcr.io/krateo-blueprints/charts/<name>` and whose `spec.chart.version` is the
     chart's own version.

   `Chart.yaml` must have an absolute https `icon` and a non-empty `keywords` list, which the
   Marketplace shows as tags.

   Every chart, in either channel, lists the repository that builds it in `Chart.yaml` `sources:`,
   as `https://github.com/<owner>/<repo>`, next to any upstream projects. That is
   how a pinned chart is traced back to the commit and CI run that built it (the installer's
   `check-pin-ci`).

   A chart meant to be pinned as an installer component must also meet the installer's component
   contract in krateo-platformops/installer. For example, a closed `values.schema.json` declares
   `global`, which is injected at install. That contract is the installer's to version, so it is
   referenced here and not copied. A publish can't catch a missing `global`: `helm lint` validates
   `values.yaml`, which has none. Copy the stamped CompositionDefinition into the chart directory
   before `helm package`, then check the archive itself: `helm package` succeeds whether the file
   is there or not.

4. **A chart's version and its CompositionDefinition's version are one number, and the release
   proves it.** The publisher refuses a CompositionDefinition whose version isn't the chart's. A
   repository's own release must also refuse a chart whose version doesn't match the version it
   claims to release. Which shape that takes depends on how the repository versions its charts:
   - **Charts that version together (the default):** the committed files carry `CHART_VERSION`,
     the release stamps it from the git tag, and tag, chart and CompositionDefinition are all one
     number.
   - **Charts that version independently:** this applies where a chart's version is a served API
     version that other charts depend on. For example, `kubernetes-cluster` names
     `composition.krateo.io/v0-6-3`, which must equal `baremetal-host` 0.6.3. Stamping every chart
     from one tag would re-point and stop serving versions for charts that didn't change. These
     repositories commit literal versions, and their release refuses any chart whose
     CompositionDefinition, or any dependent apiVersion reference, disagrees with it
     (openstack-ironic-operator-kog's `check-examples`).
   - **Charts whose author tool writes the version:** the Blueprint Composer writes a literal
     version and merging releases it. builder-scaffold's release refuses a tag, a `Chart.yaml` and
     a CompositionDefinition that differ.

   An unguarded literal is how 0.2.0 and 0.1.0 outlived every later release.

5. **Tarballs are stored in this repository's Releases.** There is one release per
   `<name>-<version>`, created with `--latest=false`, and its notes record the publishing
   repository. Because this repository is public, a chart from a private repository still
   downloads.
   - **Publishing makes a chart public.** That includes one from a private repository, so publish
     only what may be public.
   - **The caller's release page is never touched.**

6. **One owner per chart name.** The first repository to publish a name owns it. Before it writes
   anything, the publisher refuses another repository's version of that name and refuses to
   overwrite a stored version. It finds the owner from, in order: the entry's `krateo.io/source-repo`
   annotation; this repository's release notes for that version; the repository named in the
   entry's URL; the first organisation repository in the entry's `sources`.
   - **Unresolved names:** 37 names from the 2026 backfill resolve to none of these. The first
     repository to publish one after this standard claims it, and the release notes record the
     claim, so it resolves from then on.
   - **Disputes:** if the wrong repository claims a name, it is fixed here, by hand, in the
     release notes, never by publishing over it.

7. **One token: the org secret `CHARTS_PUBLISH_TOKEN`.** It is a classic PAT with `repo` scope,
   visible to all repositories, and it has no fallback. `RELEASE_FEED_TOKEN` is for the
   release-notes feed and is never used for the index. The publisher checks that the token can
   write here before it does anything else, so a dead token fails at the first step with a message
   that says so.

8. **The release isn't done until the Marketplace can install it.** The publisher reads the served
   `index.yaml` until every chart it published is listed at its version, then installs each one
   anonymously with `helm pull --repo`, the path the Marketplace uses. If either check fails, the
   release fails. Callers don't need their own check.

9. **Callers pin the publisher's full commit SHA, with its version in a comment, and let Dependabot
   upgrade it.** For example: `publish-chart.yaml@<40-character sha> # 1.0.0`. The publisher receives
   `CHARTS_PUBLISH_TOKEN`, an org-wide write token. A movable ref, whether a branch or a tag like
   `1`, would let whoever moves it run code with that token in every caller at once. A SHA can't
   move.
   - **Releases:** tags here are plain semver with no `v` prefix (the organisation's convention),
     and each release is cut as a tag such as `1.0.0` on `main`.
   - **Upgrades:** every caller has `.github/dependabot.yml` with the `github-actions` ecosystem,
     so a new publisher release arrives as a reviewed pull request in each repository rather than
     silently. That is how a fix like #5 or #6 still reaches everyone.

10. **Released commits passed lint.** The caller's release refuses a commit with no successful lint
    run. That check belongs to the caller's workflow, because only the caller knows its own lint.

11. **A blueprint declares who can see it, and whoever registers it grants that.** The portal's
    Blueprints page shows a user only the CompositionDefinitions in namespaces where they may
    `list compositiondefinitions.core.krateo.io` (krateo-platformops/portal#261). The grant belongs
    in the CompositionDefinition's namespace, which only the registrar knows. The blueprint's own
    chart renders in each instance's namespace, after an instance exists, so it can't make the
    grant. A blueprint declares its reader groups (default `admins` and `devs`, the portal's
    `blueprints-page.readerGroups`), and the grant comes from:
    - **the installer**, for catalog blueprints, through the component's `readerGroups`, which
      renders a Role and RoleBinding in the definition's namespace;
    - **a manifest published beside the CompositionDefinition**, for manual registration.
      krateo-openstack-blueprint's `portal-visibility-rbac.yaml` is an example.

## Scope

This standard covers every repository in the krateo-blueprints organisation. builder-scaffold also
seeds repositories in other owners' accounts and on self-hosted SCMs. Those have no
`CHARTS_PUBLISH_TOKEN` and publish to their own registry, so the scaffold runs the index publish
only when `github.repository_owner` is `krateo-blueprints`.

## What is never done

- **Deleting a per-chart release or a stored tarball.** About 1,247 entries indexed before this
  standard resolve through per-chart releases in the callers' repositories, and the rest resolve
  here or on gh-pages. Deleting one breaks that version for everyone.
- **Rebuilding an index from scratch.** `helm repo index` without `--merge` drops every entry whose
  tarball isn't in the directory it indexes. The old `reconcile.yaml` did exactly that, from
  gh-pages only, so it has been removed.
- **Publishing by hand.** A one-off backfill is how the index came to describe a pipeline that no
  longer existed.

## Calling the publisher

```yaml
  publish-index:
    needs: release        # your job that pushed to GHCR and uploaded the .tgz as artifact "charts-dist"
    uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@<sha> # 1.0.0
    with:
      source_repo: ${{ github.repository }}
      git_tag: ${{ github.ref_name }}
      channel: blueprints   # a repo with both kinds uploads two artifacts and calls once per channel
    secrets:
      PUBLISH_TOKEN: ${{ secrets.CHARTS_PUBLISH_TOKEN }}
```

krateo-blueprints/krateo-openstack-blueprint's `release-tag.yaml` is a complete caller covering
rules 1 to 4 and 10: placeholder stamping, the CompositionDefinition copied into each chart, archive
assertions, a lint check and the call.
