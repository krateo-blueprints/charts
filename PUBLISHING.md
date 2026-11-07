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

1. **Every chart is published twice, with the same bytes.** Once to GHCR at
   `oci://ghcr.io/krateo-blueprints/charts/<name>:<version>`, by the caller's release. Once to the
   helm index here, by `publish-chart.yaml`. A chart that is in GHCR and not in the index is not
   published, because the Marketplace installs from the index and nothing re-resolves it against
   GHCR.

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
   Marketplace shows as tags. Copy the stamped CompositionDefinition into the chart directory
   before `helm package`, then check the archive itself: `helm package` succeeds whether the file
   is there or not.

4. **Versions come from the tag.** The committed `Chart.yaml` and CompositionDefinition carry the
   `CHART_VERSION` placeholder, and the release stamps it from the git tag. Never commit a literal
   version, because literals are how 0.2.0 and 0.1.0 outlived every later release.

5. **Tarballs are stored in this repository's Releases.** There is one release per
   `<name>-<version>`, created with `--latest=false`, and its notes record the publishing
   repository. Because this repository is public, a chart from a private repository still
   downloads.
   - **Publishing makes a chart public.** That includes one from a private repository, so publish
     only what may be public.
   - **The caller's release page is never touched.**

6. **One owner per chart name.** The first repository to publish a name owns it. The publisher
   refuses another repository's version of that name, and refuses to overwrite a stored version,
   before it writes anything.

7. **One token: the org secret `CHARTS_PUBLISH_TOKEN`.** It is a classic PAT with `repo` scope,
   visible to all repositories, and it has no fallback. `RELEASE_FEED_TOKEN` is for the
   release-notes feed and is never used for the index. The publisher checks that the token can
   write here before it does anything else, so a dead token fails at the first step with a message
   that says so.

8. **The release isn't done until the Marketplace can install it.** The publisher reads the served
   `index.yaml` until every chart it published is listed at its version, then installs each one
   anonymously with `helm pull --repo`, the path the Marketplace uses. If either check fails, the
   release fails. Callers don't need their own check.

9. **Callers pin `@1`.** Tags here are plain semver with no `v` prefix, the organisation's
   convention. Every publisher release gets an immutable tag such as `1.0.0`. The major tag `1`
   moves to the newest `1.x.y`, and only for fixes that change no caller-visible input, output or
   rule. Anything else is `2.0.0`, with `2` as its major tag. Callers pin the major tag, so a fix
   reaches every repository at once, as #5 and #6 had to.

10. **Released commits passed lint.** The caller's release refuses a commit with no successful lint
    run. That check belongs to the caller's workflow, because only the caller knows its own lint.

11. **A blueprint declares who can see it.** The portal's Blueprints page shows a user only the
    CompositionDefinitions in namespaces where they may `list compositiondefinitions.core.krateo.io`
    (krateo-platformops/portal#261). Each blueprint ships a Role and RoleBinding granting that in
    its namespace to the groups it is for. The default groups are `admins` and `devs`, which are
    the portal's `blueprints-page.readerGroups`.

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
    uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@1
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
